library models;

import 'package:flutter/foundation.dart';
import 'pdb_parser.dart' as pdb;

@immutable
class DocumentInfo {
  final String path;
  final String fileName;
  final String title;
  final String creator;
  final String type;
  final int version;
  final int numRecords;
  final String format;
  final DateTime? createdAt;
  final int fileSize;

  const DocumentInfo({
    required this.path,
    required this.fileName,
    required this.title,
    required this.creator,
    required this.type,
    required this.version,
    required this.numRecords,
    required this.format,
    this.createdAt,
    required this.fileSize,
  });

  static String _basename(String p) {
    final i = p.lastIndexOf('/');
    final j = p.lastIndexOf('\\');
    final idx = i > j ? i : j;
    return idx < 0 ? p : p.substring(idx + 1);
  }

  factory DocumentInfo.fromIsiloDoc(
    pdb.IsiloDocument doc, {
    required String path,
    required int fileSize,
  }) {
    final fname = _basename(path);
    return DocumentInfo(
      path: path,
      fileName: fname,
      title: doc.name.isNotEmpty ? doc.name : fname,
      creator: doc.creator,
      type: doc.type,
      version: doc.version,
      numRecords: doc.numRecords,
      format: doc.format,
      createdAt: doc.createdAt,
      fileSize: fileSize,
    );
  }

  String get formatLabel {
    switch (format) {
      case 'iSilo3': return 'iSilo 3.x';
      case 'iSilo4': return 'iSilo 4-6.x (SilX)';
      case 'palmDoc': return 'PalmDOC';
      default: return 'Palm DB ($type/$creator)';
    }
  }

  String get fileSizeLabel {
    if (fileSize < 1024) return '$fileSize B';
    if (fileSize < 1024 * 1024) return '${(fileSize / 1024).toStringAsFixed(1)} KB';
    return '${(fileSize / 1024 / 1024).toStringAsFixed(2)} MB';
  }
}
