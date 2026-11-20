import 'dart:convert';

import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class LocalCache {
  static Database? _db;

  Future<Database> _database() async {
    if (_db != null) return _db!;
    final dir = await getApplicationDocumentsDirectory();
    final path = join(dir.path, 'nexa_erp_cache.db');
    _db = await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute(
          'CREATE TABLE cache(key TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at INTEGER NOT NULL)',
        );
      },
    );
    return _db!;
  }

  Future<void> saveJson(String key, Object value) async {
    final db = await _database();
    await db.insert(
      'cache',
      {
        'key': key,
        'data': jsonEncode(value),
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, dynamic>?> getJsonMap(String key) async {
    final db = await _database();
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    if (rows.isEmpty) return null;
    return jsonDecode(rows.first['data'] as String) as Map<String, dynamic>;
  }

  Future<DateTime?> getUpdatedAt(String key) async {
    final db = await _database();
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    if (rows.isEmpty) return null;
    final ms = rows.first['updated_at'] as int?;
    if (ms == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(ms);
  }

  Future<List<dynamic>?> getJsonList(String key) async {
    final db = await _database();
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    if (rows.isEmpty) return null;
    return jsonDecode(rows.first['data'] as String) as List<dynamic>;
  }
}

