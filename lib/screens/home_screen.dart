/// Home / Library screen
library home_screen;

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/models.dart';
import '../core/document_service.dart';
import 'reader_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final List<DocumentInfo> _library = [];
  bool _loading = false;
  String? _error;

  static const String _prefKey = 'library_paths';

  @override
  void initState() {
    super.initState();
    _loadLibrary();
  }

  Future<void> _loadLibrary() async {
    final prefs = await SharedPreferences.getInstance();
    final paths = prefs.getStringList(_prefKey) ?? [];
    if (paths.isEmpty) return;

    setState(() => _loading = true);
    final List<DocumentInfo> loaded = [];

    for (final path in paths) {
      try {
        final file = File(path);
        if (await file.exists()) {
          final result = await DocumentService.instance.openFile(path);
          loaded.add(result.info);
        }
      } catch (_) {}
    }

    if (mounted) {
      setState(() {
        _library.clear();
        _library.addAll(loaded);
        _loading = false;
      });
    }
  }

  Future<void> _saveLibrary() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_prefKey, _library.map((d) => d.path).toList());
  }

  Future<void> _pickFile() async {
    setState(() { _error = null; });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdb', 'PDB'],
        allowMultiple: true,
      );
      if (result == null || result.files.isEmpty) return;

      setState(() => _loading = true);

      for (final f in result.files) {
        final path = f.path;
        if (path == null) continue;

        // Deduplicate
        if (_library.any((d) => d.path == path)) continue;

        try {
          final opened = await DocumentService.instance.openFile(path);
          _library.add(opened.info);
        } catch (e) {
          setState(() => _error = 'Error reading ${f.name}: $e');
        }
      }

      await _saveLibrary();
      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _removeDoc(DocumentInfo doc) async {
    setState(() => _library.remove(doc));
    await _saveLibrary();
  }

  void _openDoc(DocumentInfo doc) {
    Navigator.push(context, MaterialPageRoute(
      builder: (_) => ReaderScreen(docInfo: doc),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.menu_book, size: 28),
            SizedBox(width: 8),
            Text('iSilo Recovery'),
          ],
        ),
        backgroundColor: const Color(0xFF1A237E),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: _showAbout,
            tooltip: 'About',
          ),
        ],
      ),
      body: Column(
        children: [
          // Banner
          Container(
            width: double.infinity,
            color: const Color(0xFF283593),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Text(
              'Read your iSilo .pdb documents — free, no subscription required',
              style: TextStyle(color: Colors.white.withOpacity(0.9), fontSize: 13),
            ),
          ),

          if (_error != null)
            Container(
              width: double.infinity,
              color: Colors.red.shade100,
              padding: const EdgeInsets.all(10),
              child: Row(
                children: [
                  const Icon(Icons.error_outline, color: Colors.red),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_error!, style: const TextStyle(color: Colors.red))),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => setState(() => _error = null),
                  ),
                ],
              ),
            ),

          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _library.isEmpty
                    ? _buildEmpty()
                    : _buildLibrary(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _pickFile,
        icon: const Icon(Icons.add),
        label: const Text('Open .pdb file'),
        backgroundColor: const Color(0xFF1A237E),
        foregroundColor: Colors.white,
      ),
    );
  }

  Widget _buildEmpty() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.library_books_outlined, size: 80,
              color: Colors.grey.shade400),
          const SizedBox(height: 16),
          Text('No documents yet', style: TextStyle(
            fontSize: 20, color: Colors.grey.shade600, fontWeight: FontWeight.w500,
          )),
          const SizedBox(height: 8),
          Text('Tap the button below to open a .pdb file',
              style: TextStyle(color: Colors.grey.shade500)),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _pickFile,
            icon: const Icon(Icons.folder_open),
            label: const Text('Open .pdb file'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1A237E),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLibrary() {
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: _library.length,
      itemBuilder: (_, i) => _DocCard(
        doc: _library[i],
        onTap: () => _openDoc(_library[i]),
        onRemove: () => _removeDoc(_library[i]),
      ),
    );
  }

  void _showAbout() {
    showAboutDialog(
      context: context,
      applicationName: 'iSilo Recovery',
      applicationVersion: '1.0.0',
      applicationIcon: const Icon(Icons.menu_book, size: 48, color: Color(0xFF1A237E)),
      children: const [
        Text('Read your classic iSilo .pdb documents on modern Android and Windows — for free, no subscription needed.\n\nDeveloper: seriusman0@gmail.com\n\niSilo is a trademark of DC & Co.'),
      ],
    );
  }
}

class _DocCard extends StatelessWidget {
  final DocumentInfo doc;
  final VoidCallback onTap;
  final VoidCallback onRemove;

  const _DocCard({required this.doc, required this.onTap, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 48, height: 48,
                decoration: BoxDecoration(
                  color: const Color(0xFF1A237E),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.menu_book, color: Colors.white),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(doc.title,
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                      maxLines: 2, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        _chip(doc.formatLabel, const Color(0xFFE3F2FD), const Color(0xFF1565C0)),
                        const SizedBox(width: 6),
                        _chip(doc.fileSizeLabel, const Color(0xFFF3E5F5), const Color(0xFF6A1B9A)),
                        const SizedBox(width: 6),
                        _chip('${doc.numRecords} rec', const Color(0xFFE8F5E9), const Color(0xFF2E7D32)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(doc.fileName,
                      style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                onPressed: onRemove,
                tooltip: 'Remove from library',
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(String label, Color bg, Color fg) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text(label, style: TextStyle(fontSize: 10, color: fg, fontWeight: FontWeight.w500)),
    );
  }
}
