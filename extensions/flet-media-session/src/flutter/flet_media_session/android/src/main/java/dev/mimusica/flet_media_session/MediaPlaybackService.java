package dev.mimusica.flet_media_session;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.SystemClock;

/**
 * Servicio en primer plano (tipo mediaPlayback) con una MediaSession y su notificacion:
 * mantiene viva la app con la pantalla bloqueada o en segundo plano, y muestra portada,
 * titulo, artista, progreso y los botones anterior / pausar-reanudar / siguiente.
 *
 * NO reproduce audio: solo refleja lo que Python indica con setState().
 * Todas las llamadas estaticas se hacen desde el hilo principal.
 */
public class MediaPlaybackService extends Service {

    private static final String CANAL = "mimusica_reproduccion";
    private static final int ID_NOTIFICACION = 7301;
    private static final String PREFIJO = "dev.mimusica.flet_media_session.";
    private static final String ACCION_PLAY = PREFIJO + "PLAY";
    private static final String ACCION_PAUSE = PREFIJO + "PAUSE";
    private static final String ACCION_NEXT = PREFIJO + "NEXT";
    private static final String ACCION_PREVIOUS = PREFIJO + "PREVIOUS";
    private static final String ACCION_STOP = PREFIJO + "STOP";

    private static MediaPlaybackService instancia;
    private static EstadoMedia estadoPendiente;

    private MediaSession sesion;
    private PowerManager.WakeLock bloqueoCpu;
    private EstadoMedia estado;
    private String rutaPortadaCargada;
    private Bitmap portada;

    // ---------------------------------------------------------------- API estatica
    /** Muestra o actualiza la notificacion; arranca el servicio la primera vez. */
    static void actualizar(Context contexto, EstadoMedia nuevo) {
        if (instancia != null) {
            instancia.aplicar(nuevo);
            return;
        }
        estadoPendiente = nuevo;
        Intent intent = new Intent(contexto, MediaPlaybackService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            contexto.startForegroundService(intent);
        } else {
            contexto.startService(intent);
        }
    }

    /** Quita la notificacion y detiene el servicio. */
    static void detener(Context contexto) {
        estadoPendiente = null;
        if (instancia != null) {
            instancia.cerrar();
        } else {
            contexto.stopService(new Intent(contexto, MediaPlaybackService.class));
        }
    }

    // ---------------------------------------------------------------- ciclo de vida
    @Override
    public void onCreate() {
        super.onCreate();
        instancia = this;
        crearCanal();
        sesion = new MediaSession(this, "MiMusica");
        configurarBanderas();
        sesion.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                FletMediaSessionPlugin.enviarAccion("play", 0);
            }

            @Override
            public void onPause() {
                FletMediaSessionPlugin.enviarAccion("pause", 0);
            }

            @Override
            public void onSkipToNext() {
                FletMediaSessionPlugin.enviarAccion("next", 0);
            }

            @Override
            public void onSkipToPrevious() {
                FletMediaSessionPlugin.enviarAccion("previous", 0);
            }

            @Override
            public void onStop() {
                FletMediaSessionPlugin.enviarAccion("stop", 0);
            }

            @Override
            public void onSeekTo(long posicionMs) {
                FletMediaSessionPlugin.enviarAccion("seek", posicionMs);
            }
        });
        sesion.setActive(true);
    }

    @SuppressWarnings("deprecation")
    private void configurarBanderas() {
        // Necesarias en Android < 8 para recibir botones multimedia y controles de transporte
        sesion.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS
                | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String accion = intent != null ? intent.getAction() : null;
        if (accion != null) {
            // Boton de la notificacion
            manejarBoton(accion);
            return START_NOT_STICKY;
        }
        EstadoMedia e = estadoPendiente != null ? estadoPendiente : estado;
        estadoPendiente = null;
        if (e == null) {
            // Nada que mostrar: hay que cumplir con startForeground antes de salir.
            iniciarPrimerPlano(notificacionMinima());
            cerrar();
            return START_NOT_STICKY;
        }
        aplicar(e);
        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // El usuario cerro la app desde recientes: sin motor de Flutter no hay audio.
        cerrar();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        liberarBloqueo();
        if (sesion != null) {
            sesion.setActive(false);
            sesion.release();
            sesion = null;
        }
        if (instancia == this) {
            instancia = null;
        }
        super.onDestroy();
    }

    // ---------------------------------------------------------------- botones
    private void manejarBoton(String accion) {
        switch (accion) {
            case ACCION_PLAY:
                FletMediaSessionPlugin.enviarAccion("play", 0);
                break;
            case ACCION_PAUSE:
                FletMediaSessionPlugin.enviarAccion("pause", 0);
                break;
            case ACCION_NEXT:
                FletMediaSessionPlugin.enviarAccion("next", 0);
                break;
            case ACCION_PREVIOUS:
                FletMediaSessionPlugin.enviarAccion("previous", 0);
                break;
            case ACCION_STOP:
                FletMediaSessionPlugin.enviarAccion("stop", 0);
                break;
            default:
                break;
        }
    }

    // ---------------------------------------------------------------- estado
    void aplicar(EstadoMedia nuevo) {
        if (sesion == null) {
            return;
        }
        estado = nuevo;
        actualizarSesion();
        iniciarPrimerPlano(construirNotificacion());
        gestionarBloqueoCpu();
    }

    void cerrar() {
        estado = null;
        if (instancia == this) {
            instancia = null; // las siguientes llamadas arrancaran un servicio nuevo
        }
        liberarBloqueo();
        if (Build.VERSION.SDK_INT >= 24) {
            stopForeground(Service.STOP_FOREGROUND_REMOVE);
        } else {
            stopForeground(true);
        }
        stopSelf();
    }

    private void iniciarPrimerPlano(Notification notificacion) {
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(ID_NOTIFICACION, notificacion,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } else {
                startForeground(ID_NOTIFICACION, notificacion);
            }
        } catch (RuntimeException ex) {
            // Si el sistema no permite el primer plano, al menos se muestra la notificacion.
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.notify(ID_NOTIFICACION, notificacion);
            }
        }
    }

    private void actualizarSesion() {
        MediaMetadata.Builder metadatos = new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, estado.titulo)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, estado.artista)
                .putString(MediaMetadata.METADATA_KEY_ALBUM, estado.album);
        if (estado.duracionMs > 0) {
            metadatos.putLong(MediaMetadata.METADATA_KEY_DURATION, estado.duracionMs);
        }
        Bitmap imagen = cargarPortada();
        if (imagen != null) {
            metadatos.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, imagen);
            metadatos.putBitmap(MediaMetadata.METADATA_KEY_ART, imagen);
        }
        sesion.setMetadata(metadatos.build());

        long acciones = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
                | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_SEEK_TO
                | PlaybackState.ACTION_STOP;
        PlaybackState estadoReproduccion = new PlaybackState.Builder()
                .setActions(acciones)
                .setState(estado.reproduciendo ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        estado.posicionMs,
                        estado.reproduciendo ? 1.0f : 0.0f,
                        SystemClock.elapsedRealtime())
                .build();
        sesion.setPlaybackState(estadoReproduccion);
    }

    // ---------------------------------------------------------------- notificacion
    private void crearCanal() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel canal = new NotificationChannel(
                    CANAL, "Reproduccion de musica", NotificationManager.IMPORTANCE_LOW);
            canal.setShowBadge(false);
            canal.setSound(null, null);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.createNotificationChannel(canal);
            }
        }
    }

    private Notification.Builder nuevoConstructor() {
        return Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CANAL)
                : new Notification.Builder(this);
    }

    private Notification notificacionMinima() {
        return nuevoConstructor()
                .setSmallIcon(R.drawable.ic_mimusica_notificacion)
                .setContentTitle("Mi Musica")
                .build();
    }

    private Notification.Action boton(int icono, String texto, String accion, int codigo) {
        Intent intent = new Intent(this, MediaPlaybackService.class).setAction(accion);
        PendingIntent pendiente = PendingIntent.getService(this, codigo, intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Action.Builder(Icon.createWithResource(this, icono), texto, pendiente).build();
    }

    private Notification construirNotificacion() {
        Notification.Builder b = nuevoConstructor()
                .setSmallIcon(R.drawable.ic_mimusica_notificacion)
                .setContentTitle(estado.titulo)
                .setContentText(estado.artista)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setCategory(Notification.CATEGORY_TRANSPORT)
                .setOnlyAlertOnce(true)
                .setOngoing(estado.reproduciendo)
                // Minuto:segundo transcurrido, que avanza solo mientras suena
                .setShowWhen(estado.reproduciendo)
                .setUsesChronometer(estado.reproduciendo)
                .setWhen(System.currentTimeMillis() - estado.posicionMs);
        if (!estado.album.isEmpty()) {
            b.setSubText(estado.album);
        }
        Bitmap imagen = cargarPortada();
        if (imagen != null) {
            b.setLargeIcon(imagen);
        }
        PendingIntent abrir = intentAbrirApp();
        if (abrir != null) {
            b.setContentIntent(abrir);
        }
        // Al descartar la notificacion (cuando esta en pausa) se detiene la reproduccion
        Intent detener = new Intent(this, MediaPlaybackService.class).setAction(ACCION_STOP);
        b.setDeleteIntent(PendingIntent.getService(this, 5, detener,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        if (Build.VERSION.SDK_INT >= 31) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }

        b.addAction(boton(R.drawable.ic_mimusica_anterior, "Anterior", ACCION_PREVIOUS, 1));
        if (estado.reproduciendo) {
            b.addAction(boton(R.drawable.ic_mimusica_pausa, "Pausar", ACCION_PAUSE, 2));
        } else {
            b.addAction(boton(R.drawable.ic_mimusica_reproducir, "Reproducir", ACCION_PLAY, 3));
        }
        b.addAction(boton(R.drawable.ic_mimusica_siguiente, "Siguiente", ACCION_NEXT, 4));

        b.setStyle(new Notification.MediaStyle()
                .setMediaSession(sesion.getSessionToken())
                .setShowActionsInCompactView(0, 1, 2));
        return b.build();
    }

    private PendingIntent intentAbrirApp() {
        Intent abrir = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (abrir == null) {
            return null;
        }
        abrir.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(this, 0, abrir,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    // ---------------------------------------------------------------- portada y CPU
    /** Decodifica la portada (reduciendola) y la guarda hasta que cambie la ruta. */
    private Bitmap cargarPortada() {
        String ruta = estado != null ? estado.rutaPortada : null;
        if (ruta == null || ruta.isEmpty()) {
            rutaPortadaCargada = null;
            portada = null;
            return null;
        }
        if (ruta.equals(rutaPortadaCargada)) {
            return portada;
        }
        BitmapFactory.Options opciones = new BitmapFactory.Options();
        opciones.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(ruta, opciones);
        int mayor = Math.max(opciones.outWidth, opciones.outHeight);
        int muestreo = 1;
        while (mayor / muestreo > 640) {
            muestreo *= 2;
        }
        opciones.inJustDecodeBounds = false;
        opciones.inSampleSize = muestreo;
        portada = BitmapFactory.decodeFile(ruta, opciones);
        rutaPortadaCargada = ruta;
        return portada;
    }

    /** Mientras suena, la CPU no se duerme: asi Python puede pasar a la siguiente cancion. */
    private void gestionarBloqueoCpu() {
        if (estado != null && estado.reproduciendo) {
            if (bloqueoCpu == null) {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (pm == null) {
                    return;
                }
                bloqueoCpu = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "mimusica:reproduccion");
                bloqueoCpu.setReferenceCounted(false);
            }
            if (!bloqueoCpu.isHeld()) {
                bloqueoCpu.acquire(6L * 60L * 60L * 1000L); // tope de seguridad: 6 horas
            }
        } else {
            liberarBloqueo();
        }
    }

    private void liberarBloqueo() {
        if (bloqueoCpu != null && bloqueoCpu.isHeld()) {
            bloqueoCpu.release();
        }
    }
}
