/// Document service: open, cache, and read .pdb files
library document_service;

import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'pdb_parser.dart' as pdb_parser;
import 'models.dart';

class DocumentService {
  DocumentService._();
  static final DocumentService instance = DocumentService._();

  final Map<String, pdb_parser.IsiloDocument> _cache = {};

  Future<({DocumentInfo info, pdb_parser.IsiloDocument doc})> openFile(String path) async {
    final file = File(path);
    if (!await file.exists()) {
      throw pdb_parser.PdbParseException('File not found: $path');
    }
    final bytes = await file.readAsBytes();
    final doc = await compute(_parsePdbIsolate, bytes);
    _cache[path] = doc;
    final info = DocumentInfo.fromIsiloDoc(doc, path: path, fileSize: bytes.length);
    return (info: info, doc: doc);
  }

  Future<pdb_parser.IsiloDocument> getDoc(String path) async {
    if (_cache.containsKey(path)) return _cache[path]!;
    final result = await openFile(path);
    return result.doc;
  }

  Future<String> extractText(String path) async {
    final doc = await getDoc(path);
    return pdb_parser.extractText(doc);
  }

  void clearCache() => _cache.clear();
}

pdb_parser.IsiloDocument _parsePdbIsolate(Uint8List data) {
  return pdb_parser.parsePdb(data);
}
