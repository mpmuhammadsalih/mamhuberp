import 'package:flutter/foundation.dart';

/// Tracks in-flight save / mutation API calls for a global blocking overlay.
class TransactionOverlayController extends ChangeNotifier {
  int _pending = 0;

  bool get isBusy => _pending > 0;

  void begin() {
    _pending++;
    notifyListeners();
  }

  void end() {
    if (_pending > 0) {
      _pending--;
      notifyListeners();
    }
  }
}
