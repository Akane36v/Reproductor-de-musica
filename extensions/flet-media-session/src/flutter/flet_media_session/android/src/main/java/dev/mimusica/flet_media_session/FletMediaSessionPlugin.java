package dev.mimusica.flet_media_session;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import java.util.HashMap;
import java.util.Map;

import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.embedding.engine.plugins.activity.ActivityAware;
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import io.flutter.plugin.common.MethodChannel.MethodCallHandler;
import io.flutter.plugin.common.MethodChannel.Result;
import io.flutter.plugin.common.PluginRegistry;

/**
 * Puente entre Dart (canal "mimusica/media_session") y el servicio en primer plano.
 * Dart -> nativo: setState, stop, requestPermissions.
 * Nativo -> Dart: onAction (play, pause, next, previous, stop, seek).
 */
public class FletMediaSessionPlugin implements FlutterPlugin, MethodCallHandler, ActivityAware,
        PluginRegistry.RequestPermissionsResultListener {

    private static final String NOMBRE_CANAL = "mimusica/media_session";
    private static final int CODIGO_PERMISO = 7302;
    private static final Handler HILO_PRINCIPAL = new Handler(Looper.getMainLooper());

    private static volatile MethodChannel canal;

    private Context contexto;
    private Activity actividad;
    private ActivityPluginBinding enlaceActividad;
    private Result permisoPendiente;

    // ---- FlutterPlugin ----------------------------------------------------------
    @Override
    public void onAttachedToEngine(FlutterPluginBinding binding) {
        contexto = binding.getApplicationContext();
        canal = new MethodChannel(binding.getBinaryMessenger(), NOMBRE_CANAL);
        canal.setMethodCallHandler(this);
    }

    @Override
    public void onDetachedFromEngine(FlutterPluginBinding binding) {
        // Sin motor de Flutter tampoco hay audio: se retira la notificacion.
        if (contexto != null) {
            MediaPlaybackService.detener(contexto);
        }
        if (canal != null) {
            canal.setMethodCallHandler(null);
        }
        canal = null;
        contexto = null;
    }

    // ---- MethodCallHandler --------------------------------------------------------
    @Override
    public void onMethodCall(MethodCall call, Result result) {
        switch (call.method) {
            case "setState": {
                Map<String, Object> argumentos = call.arguments();
                if (argumentos == null || contexto == null) {
                    result.error("estado", "Faltan argumentos o contexto", null);
                    return;
                }
                MediaPlaybackService.actualizar(contexto, EstadoMedia.desde(argumentos));
                result.success(null);
                break;
            }
            case "stop":
                if (contexto != null) {
                    MediaPlaybackService.detener(contexto);
                }
                result.success(null);
                break;
            case "requestPermissions":
                pedirPermisoNotificaciones(result);
                break;
            default:
                result.notImplemented();
        }
    }

    /** Lo llama el servicio cuando el usuario pulsa un boton; se reenvia a Dart en el hilo principal. */
    static void enviarAccion(final String accion, final long posicionMs) {
        HILO_PRINCIPAL.post(new Runnable() {
            @Override
            public void run() {
                MethodChannel c = canal;
                if (c != null) {
                    Map<String, Object> datos = new HashMap<>();
                    datos.put("action", accion);
                    datos.put("position", posicionMs);
                    c.invokeMethod("onAction", datos);
                }
            }
        });
    }

    // ---- Permiso de notificaciones (Android 13+) ---------------------------------
    private void pedirPermisoNotificaciones(Result result) {
        if (Build.VERSION.SDK_INT < 33 || contexto == null) {
            result.success(true);
            return;
        }
        if (contexto.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            result.success(true);
            return;
        }
        if (actividad == null || permisoPendiente != null) {
            result.success(false);
            return;
        }
        permisoPendiente = result;
        actividad.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, CODIGO_PERMISO);
    }

    @Override
    public boolean onRequestPermissionsResult(int codigo, String[] permisos, int[] resultados) {
        if (codigo != CODIGO_PERMISO) {
            return false;
        }
        boolean concedido = resultados.length > 0 && resultados[0] == PackageManager.PERMISSION_GRANTED;
        if (permisoPendiente != null) {
            permisoPendiente.success(concedido);
            permisoPendiente = null;
        }
        return true;
    }

    // ---- ActivityAware --------------------------------------------------------------
    @Override
    public void onAttachedToActivity(ActivityPluginBinding binding) {
        actividad = binding.getActivity();
        enlaceActividad = binding;
        binding.addRequestPermissionsResultListener(this);
    }

    @Override
    public void onDetachedFromActivityForConfigChanges() {
        soltarActividad();
    }

    @Override
    public void onReattachedToActivityForConfigChanges(ActivityPluginBinding binding) {
        onAttachedToActivity(binding);
    }

    @Override
    public void onDetachedFromActivity() {
        soltarActividad();
    }

    private void soltarActividad() {
        if (enlaceActividad != null) {
            enlaceActividad.removeRequestPermissionsResultListener(this);
        }
        enlaceActividad = null;
        actividad = null;
    }
}
