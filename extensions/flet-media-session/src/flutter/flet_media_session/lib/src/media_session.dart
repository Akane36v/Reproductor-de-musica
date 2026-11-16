import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Puente entre el control Python `MediaSession` y el plugin nativo de Android.
class MediaSessionService extends FletService {
  MediaSessionService({required super.control});

  static const MethodChannel _channel = MethodChannel('mimusica/media_session');

  @override
  void init() {
    super.init();
    debugPrint("MediaSession(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
    // Botones de la notificacion -> evento "action" hacia Python
    _channel.setMethodCallHandler(_onNativeCall);
  }

  Future<dynamic> _onNativeCall(MethodCall call) async {
    if (call.method == 'onAction') {
      final args = Map<String, dynamic>.from(call.arguments as Map);
      control.triggerEvent("action", {
        "action": args["action"],
        "position": args["position"] ?? 0,
      });
    }
    return null;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("MediaSession.$name");
    if (defaultTargetPlatform != TargetPlatform.android) {
      // Solo Android tiene implementación nativa; en el resto no se hace nada.
      return name == "request_permissions" ? false : null;
    }
    try {
      switch (name) {
        case "request_permissions":
          return await _channel.invokeMethod<bool>('requestPermissions') ?? false;
        case "set_state":
          await _channel.invokeMethod('setState', args);
          return null;
        case "stop":
          await _channel.invokeMethod('stop');
          return null;
        default:
          throw Exception("Unknown MediaSession method: $name");
      }
    } on MissingPluginException {
      return name == "request_permissions" ? false : null;
    }
  }

  @override
  void dispose() {
    debugPrint("MediaSession(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    _channel.setMethodCallHandler(null);
    super.dispose();
  }
}
