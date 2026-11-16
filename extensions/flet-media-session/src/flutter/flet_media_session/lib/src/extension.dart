import 'package:flet/flet.dart';

import 'media_session.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "MediaSession":
        return MediaSessionService(control: control);
      default:
        return null;
    }
  }
}
