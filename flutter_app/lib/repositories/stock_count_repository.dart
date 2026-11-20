import '../models/stock_count_session.dart';
import '../services/stock_count_service.dart';

class StockCountRepository {
  StockCountRepository(this._service);

  final StockCountService _service;

  Future<List<StockCountSummary>> listAvailableDrafts({int? locationcode}) =>
      _service.listSessions(
        locationcode: locationcode,
        status: 'OPEN',
        availableForUser: false,
      );

  Future<StockCountSession> claimSession({
    required int locationcode,
    required int countNo,
  }) =>
      _service.claimSession(locationcode: locationcode, countNo: countNo);

  Future<StockCountSession> loadSession(int locationcode, int countNo) =>
      _service.getSession(locationcode, countNo);

  Future<StockCountLine> saveLine({
    required int locationcode,
    required int countNo,
    required String itemcode,
    required double countedQty,
    required double systemQty,
    String uom = '',
    String barcode = '',
    int? warehouseId,
  }) =>
      _service.upsertLine(
        locationcode: locationcode,
        countNo: countNo,
        itemcode: itemcode,
        countedQty: countedQty,
        systemQty: systemQty,
        uom: uom,
        barcode: barcode,
        warehouseId: warehouseId,
      );

  Future<void> removeLine({
    required int locationcode,
    required int countNo,
    required String itemcode,
  }) =>
      _service.deleteLineByItem(
        locationcode: locationcode,
        countNo: countNo,
        itemcode: itemcode,
      );

  Future<StockCountSession> postSession({
    required int locationcode,
    required int countNo,
  }) =>
      _service.postSession(locationcode: locationcode, countNo: countNo);
}
