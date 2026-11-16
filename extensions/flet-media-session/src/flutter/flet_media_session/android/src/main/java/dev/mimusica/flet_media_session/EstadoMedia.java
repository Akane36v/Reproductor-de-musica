package dev.mimusica.flet_media_session;

import java.util.Map;

/** Lo que Python quiere mostrar en la notificacion multimedia. */
final class EstadoMedia {
    final String titulo;
    final String artista;
    final String album;
    final long duracionMs;
    final long posicionMs;
    final boolean reproduciendo;
    final String rutaPortada;

    EstadoMedia(String titulo, String artista, String album, long duracionMs, long posicionMs,
                boolean reproduciendo, String rutaPortada) {
        this.titulo = titulo;
        this.artista = artista;
        this.album = album;
        this.duracionMs = duracionMs;
        this.posicionMs = posicionMs;
        this.reproduciendo = reproduciendo;
        this.rutaPortada = rutaPortada;
    }

    private static String texto(Object valor) {
        return valor == null ? "" : String.valueOf(valor);
    }

    private static long numero(Object valor) {
        return valor instanceof Number ? ((Number) valor).longValue() : 0L;
    }

    static EstadoMedia desde(Map<String, Object> m) {
        Object portada = m.get("artPath");
        return new EstadoMedia(
                texto(m.get("title")),
                texto(m.get("artist")),
                texto(m.get("album")),
                numero(m.get("durationMs")),
                numero(m.get("positionMs")),
                Boolean.TRUE.equals(m.get("playing")),
                portada == null ? null : String.valueOf(portada));
    }
}
