import 'package:flutter/material.dart';

import '../core/network/provider_api_error.dart';
import '../models/inventory_item.dart';
import '../repositories/inventory_repository.dart';

class InventoryProvider extends ChangeNotifier {
  InventoryProvider(this._repository);

  final InventoryRepository _repository;

  bool isLoading = false;
  bool isFetching = false;
  String? error;
  Object? errorCause;
  List<InventoryItem> items = [];

  Future<void> load({int page = 1, int pageSize = 20}) async {
    error = null;
    errorCause = null;
    isFetching = true;
    if (items.isEmpty) {
      isLoading = true;
    }
    notifyListeners();
    try {
      items = await _repository.getInventory(page: page, pageSize: pageSize);
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
    } finally {
      isLoading = false;
      isFetching = false;
      notifyListeners();
    }
  }
}

