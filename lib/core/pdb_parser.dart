/// iSilo PDB (Palm Database) parser
/// Supports iSilo 3.x, 4.x, 5.x, 6.x document formats
/// Format: Palm Database header + iSilo-specific record compression
///
/// PDB Header layout (78 bytes):
///   0-31  : name (null-padded)
///   32-33 : attributes
///   34-35 : version
///   36-39 : creationDate (seconds since Jan 1, 1904)
///   40-43 : modificationDate
///   44-47 : lastBackupDate
///   48-51 : modificationNumber
///   52-55 : appInfoID
///   56-59 : sortInfoID
///   60-63 : type (4 chars)
///   64-67 : creator (4 chars)
///   68-71 : uniqueIDSeed
///   72-75 : nextRecordListID
///   76-77 : numRecords
///   78+   : record list (8 bytes each: 4=offset, 1=attributes, 3=uniqueID)
library pdb_parser;

import 'dart:convert';
import 'dart:io' show zlib;
import 'dart:typed_data';
import 'package:flutter/foundation.dart';

/// Known iSilo creator/type combos:
///   type="iSil", creator="iSil"  -> iSilo 3.x
///   type="SilX", creator="iSil"  -> iSilo 4.x+
///   type="TEXt", creator="REAd"  -> PalmDOC (also readable)
const Set<String> _kSupportedCreators = {'iSil'};
const Set<String> _kSupportedTypes = {'iSil', 'SilX', 'TEXt', 'PNRd', 'DataSrc'};

/// iSilo record 0 header (version 4/5/6 "SilX")
///  Offset  Size  Description
///   0       2    version (big-endian)
///   2       2    flags
///   4       4    uncompressedSize
///   8       4    numTextRecords
///  12       4    recordSize (usually 4096)
///  16+      var  channel/section info

class PdbParseException implements Exception {
  final String message;
  PdbParseException(this.message);
  @override
  String toString() => 'PdbParseException: $message';
}

class PdbRecord {
  final int offset;
  final int length;
  final int attributes;
  final Uint8List data;

  const PdbRecord({
    required this.offset,
    required this.length,
    required this.attributes,
    required this.data,
  });
}

class IsiloDocument {
  final String name;
  final String type;
  final String creator;
  final int version;
  final int numRecords;
  final List<PdbRecord> records;
  final String format; // 'iSilo3', 'iSilo4', 'palmDoc', 'unknown'
  final DateTime? createdAt;

  const IsiloDocument({
    required this.name,
    required this.type,
    required this.creator,
    required this.version,
    required this.numRecords,
    required this.records,
    required this.format,
    this.createdAt,
  });
}

/// Main entry point: parse a .pdb file bytes into an IsiloDocument
IsiloDocument parsePdb(Uint8List data) {
  if (data.length < 78) {
    throw PdbParseException('File too small to be a PDB (${data.length} bytes)');
  }

  final bd = data.buffer.asByteData();

  // Read name (bytes 0-31, null-terminated latin-1)
  final nameBytes = data.sublist(0, 32);
  final nameEnd = nameBytes.indexOf(0);
  final name = latin1.decode(nameEnd >= 0 ? nameBytes.sublist(0, nameEnd) : nameBytes);

  // type/creator at offsets 60/64
  final type    = latin1.decode(data.sublist(60, 64));
  final creator = latin1.decode(data.sublist(64, 68));

  final numRecords = bd.getUint16(76, Endian.big);
  if (numRecords == 0) {
    throw PdbParseException('PDB has no records');
  }

  // Creation date: Palm epoch = Jan 1 1904
  final palmEpochOffset = 2082844800; // seconds between 1904 and 1970
  final cdate = bd.getUint32(36, Endian.big);
  DateTime? createdAt;
  if (cdate > 0) {
    try {
      createdAt = DateTime.fromMillisecondsSinceEpoch(
          (cdate - palmEpochOffset) * 1000, isUtc: true);
    } catch (_) {}
  }

  // Parse record list
  final int recordListStart = 78;
  final List<PdbRecord> records = [];

  for (int i = 0; i < numRecords; i++) {
    final int entryOffset = recordListStart + i * 8;
    if (entryOffset + 8 > data.length) break;

    final int recOffset = bd.getUint32(entryOffset, Endian.big);
    final int recAttr   = data[entryOffset + 4];

    final int recEnd = (i + 1 < numRecords)
        ? bd.getUint32(recordListStart + (i + 1) * 8, Endian.big)
        : data.length;

    if (recOffset > data.length || recEnd > data.length || recOffset > recEnd) {
      continue;
    }

    final recData = data.sublist(recOffset, recEnd);
    records.add(PdbRecord(
      offset: recOffset,
      length: recEnd - recOffset,
      attributes: recAttr,
      data: recData,
    ));
  }

  if (records.isEmpty) {
    throw PdbParseException('No valid records found in PDB');
  }

  // Detect format
  String format;
  if (creator == 'iSil' && type == 'SilX') {
    format = 'iSilo4';
  } else if (creator == 'iSil' && type == 'iSil') {
    format = 'iSilo3';
  } else if (creator == 'REAd' && type == 'TEXt') {
    format = 'palmDoc';
  } else {
    format = 'unknown';
  }

  // version from record 0 header
  int version = 0;
  if (records[0].data.length >= 2) {
    final r0bd = records[0].data.buffer.asByteData(records[0].data.offsetInBytes);
    version = r0bd.getUint16(0, Endian.big);
  }

  return IsiloDocument(
    name: name,
    type: type,
    creator: creator,
    version: version,
    numRecords: numRecords,
    records: records,
    format: format,
    createdAt: createdAt,
  );
}

/// ===== TEXT EXTRACTION =====
/// Extract readable text from an iSilo document.
/// Returns raw text (with HTML markup for iSilo4, plain for palmDoc).
Future<String> extractText(IsiloDocument doc) async {
  if (doc.format == 'palmDoc') {
    return _extractPalmDoc(doc);
  } else if (doc.format == 'iSilo3' || doc.format == 'iSilo4') {
    return _extractIsiloText(doc);
  }
  return _extractRaw(doc);
}

/// Extract PalmDOC format (simple LZ77 compression or uncompressed)
String _extractPalmDoc(IsiloDocument doc) {
  if (doc.records.isEmpty) return '';

  final r0 = doc.records[0];
  if (r0.data.length < 16) return '';
  final r0bd = r0.data.buffer.asByteData(r0.data.offsetInBytes);
  final compression = r0bd.getUint16(0, Endian.big); // 1=none, 2=palmdoc lz77

  final buf = StringBuffer();
  // Text records start at index 1
  for (int i = 1; i < doc.records.length; i++) {
    final recData = doc.records[i].data;
    if (compression == 2) {
      final decoded = _palmDocDecompress(recData);
      buf.write(latin1.decode(decoded));
    } else {
      buf.write(latin1.decode(recData));
    }
  }
  return buf.toString();
}

/// PalmDOC LZ77 decompression
Uint8List _palmDocDecompress(Uint8List input) {
  final out = <int>[];
  int i = 0;
  while (i < input.length) {
    final c = input[i++];
    if (c == 0) {
      out.add(0);
    } else if (c <= 8) {
      // literal copy of next c bytes
      for (int j = 0; j < c && i < input.length; j++) {
        out.add(input[i++]);
      }
    } else if (c <= 0x7F) {
      out.add(c);
    } else if (c <= 0xBF) {
      // 2-byte sequence: backref
      if (i >= input.length) break;
      final n = input[i++];
      final dist = ((c & 0x3F) << 8) | n;
      final length = (dist & 0x7) + 3;
      final offset = (dist >> 3) & 0x1FFF;
      final start = out.length - offset;
      for (int j = 0; j < length; j++) {
        out.add(start + j >= 0 && start + j < out.length ? out[start + j] : 0x20);
      }
    } else if (c <= 0xFF) {
      // space + char
      out.add(0x20);
      out.add(c ^ 0x80);
    }
  }
  return Uint8List.fromList(out);
}

/// iSilo 3.x/4.x/5.x/6.x text extraction
/// iSilo uses custom huffman/LZ compression on records 1+
/// Record 0 is the document header/TOC
String _extractIsiloText(IsiloDocument doc) {
  final buf = StringBuffer();

  if (doc.records.isEmpty) return '';

  // Try to extract raw HTML/text from records starting at index 1
  // iSilo 4+ (SilX) records contain zlib-deflated HTML blocks
  for (int i = 1; i < doc.records.length && i < 500; i++) {
    final recData = doc.records[i].data;
    if (recData.isEmpty) continue;

    // Try zlib decompression (iSilo 4+)
    final decompressed = _tryZlibDecompress(recData);
    if (decompressed != null && decompressed.isNotEmpty) {
      try {
        final text = utf8.decode(decompressed, allowMalformed: true);
        if (_looksLikeText(text)) {
          buf.write(text);
          continue;
        }
      } catch (_) {}
      try {
        final text = latin1.decode(decompressed);
        if (_looksLikeText(text)) {
          buf.write(text);
          continue;
        }
      } catch (_) {}
    }

    // Try raw text (uncompressed record)
    if (_looksLikeRawText(recData)) {
      try {
        final text = utf8.decode(recData, allowMalformed: true);
        buf.write(text);
        continue;
      } catch (_) {
        try {
          buf.write(latin1.decode(recData));
          continue;
        } catch (_) {}
      }
    }
  }

  final result = buf.toString().trim();
  if (result.isEmpty) {
    // Fallback: extract all printable ASCII from whole file
    return _extractRaw(doc);
  }
  return result;
}

/// Try to decompress zlib data, trying both with and without header
Uint8List? _tryZlibDecompress(Uint8List data) {
  // iSilo SilX records: try starting at offset 0, 2, 4, 8
  for (int start = 0; start <= 8 && start < data.length; start++) {
    try {
      final slice = data.sublist(start);
      final decoded = zlib.decode(slice);
      if (decoded.isNotEmpty) return Uint8List.fromList(decoded);
    } catch (_) {}
    // Try raw deflate (no header)
    try {
      final slice = data.sublist(start);
      final decoded = _rawDeflate(slice);
      if (decoded != null && decoded.isNotEmpty) return decoded;
    } catch (_) {}
  }
  return null;
}

/// Minimal raw deflate (no zlib header) - fallback
Uint8List? _rawDeflate(Uint8List data) {
  try {
    // Add fake zlib header: 0x78 0x9C
    final withHeader = Uint8List(data.length + 2);
    withHeader[0] = 0x78;
    withHeader[1] = 0x9C;
    withHeader.setRange(2, withHeader.length, data);
    final decoded = zlib.decode(withHeader);
    return Uint8List.fromList(decoded);
  } catch (_) {
    return null;
  }
}

bool _looksLikeText(String s) {
  if (s.isEmpty) return false;
  int printable = 0;
  for (final c in s.codeUnits.take(200)) {
    if ((c >= 32 && c < 127) || c == 9 || c == 10 || c == 13) printable++;
  }
  return printable > s.codeUnits.take(200).length * 0.6;
}

bool _looksLikeRawText(Uint8List data) {
  if (data.isEmpty) return false;
  int printable = 0;
  final sample = data.length > 200 ? data.sublist(0, 200) : data;
  for (final b in sample) {
    if ((b >= 32 && b < 127) || b == 9 || b == 10 || b == 13) printable++;
  }
  return printable > sample.length * 0.7;
}

/// Last resort: extract all printable text from records
String _extractRaw(IsiloDocument doc) {
  final buf = StringBuffer();
  for (final rec in doc.records.skip(1).take(100)) {
    for (final b in rec.data) {
      if ((b >= 32 && b < 127) || b == 10 || b == 13) {
        buf.writeCharCode(b);
      } else if (b == 9) {
        buf.write(' ');
      }
    }
    buf.write('\n');
  }
  return buf.toString();
}

// dart:io zlib wrapper used via import at top of file
