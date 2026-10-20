/// Reader screen: display document content
library reader_screen;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/models.dart';
import '../core/document_service.dart';

class ReaderScreen extends StatefulWidget {
  final DocumentInfo docInfo;
  const ReaderScreen({super.key, required this.docInfo});

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  String? _text;
  bool _loading = true;
  String? _error;
  double _fontSize = 16;
  bool _isDark = false;
  String _viewMode = 'text'; // 'text' or 'html' or 'hex'
  final ScrollController _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    _loadDocument();
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadDocument() async {
    setState(() { _loading = true; _error = null; });
    try {
      final text = await DocumentService.instance.extractText(widget.docInfo.path);
      if (mounted) setState(() { _text = text; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  void _copyText() {
    if (_text == null) return;
    Clipboard.setData(ClipboardData(text: _text!));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Text copied to clipboard')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _isDark ? const Color(0xFF121212) : Colors.white,
      appBar: AppBar(
        title: Text(widget.docInfo.title,
          style: const TextStyle(fontSize: 16),
          overflow: TextOverflow.ellipsis,
        ),
        backgroundColor: const Color(0xFF1A237E),
        foregroundColor: Colors.white,
        actions: [
          // Font size
          IconButton(
            icon: const Icon(Icons.text_decrease),
            onPressed: () => setState(() => _fontSize = (_fontSize - 1).clamp(10, 32)),
            tooltip: 'Smaller text',
          ),
          IconButton(
            icon: const Icon(Icons.text_increase),
            onPressed: () => setState(() => _fontSize = (_fontSize + 1).clamp(10, 32)),
            tooltip: 'Larger text',
          ),
          // Dark mode
          IconButton(
            icon: Icon(_isDark ? Icons.light_mode : Icons.dark_mode),
            onPressed: () => setState(() => _isDark = !_isDark),
            tooltip: 'Toggle dark mode',
          ),
          // Copy
          IconButton(
            icon: const Icon(Icons.copy),
            onPressed: _text != null ? _copyText : null,
            tooltip: 'Copy text',
          ),
          // View mode
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            onSelected: (v) => setState(() => _viewMode = v),
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'text', child: Text('Plain text view')),
              const PopupMenuItem(value: 'html', child: Text('HTML view')),
              const PopupMenuItem(value: 'info', child: Text('Document info')),
            ],
          ),
        ],
      ),
      body: _loading
          ? _buildLoading()
          : _error != null
              ? _buildError()
              : _viewMode == 'info'
                  ? _buildInfo()
                  : _buildReader(),
    );
  }

  Widget _buildLoading() {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Extracting document content...'),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.redAccent),
            const SizedBox(height: 16),
            Text('Failed to read document', style: TextStyle(
              fontSize: 18, fontWeight: FontWeight.bold,
              color: _isDark ? Colors.white : Colors.black87,
            )),
            const SizedBox(height: 8),
            Text(_error ?? 'Unknown error', textAlign: TextAlign.center,
              style: TextStyle(color: _isDark ? Colors.white70 : Colors.black54)),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _loadDocument,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildReader() {
    if (_text == null || _text!.trim().isEmpty) {
      return _buildEmpty();
    }

    final textColor = _isDark ? Colors.white.withOpacity(0.9) : const Color(0xFF1A1A2E);
    final bgColor   = _isDark ? const Color(0xFF1E1E2E) : const Color(0xFFFAFAFA);

    return Column(
      children: [
        // Stats bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          color: _isDark ? const Color(0xFF2A2A3E) : const Color(0xFFEEEEEE),
          child: Row(
            children: [
              Text(
                '${_text!.length} chars · ${_text!.split('\n').length} lines',
                style: TextStyle(fontSize: 11, color: _isDark ? Colors.white60 : Colors.black54),
              ),
              const Spacer(),
              _formatBadge(widget.docInfo.formatLabel),
            ],
          ),
        ),
        Expanded(
          child: Container(
            color: bgColor,
            child: Scrollbar(
              controller: _scrollCtrl,
              thumbVisibility: true,
              child: SingleChildScrollView(
                controller: _scrollCtrl,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                child: _viewMode == 'html'
                    ? _buildHtmlView(textColor)
                    : SelectableText(
                        _text!,
                        style: TextStyle(
                          fontSize: _fontSize,
                          color: textColor,
                          fontFamily: 'monospace',
                          height: 1.55,
                        ),
                      ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHtmlView(Color textColor) {
    // Strip HTML tags for safe display since flutter_html may not be available
    final plainText = _text!.replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ').trim();
    return SelectableText(
      plainText,
      style: TextStyle(fontSize: _fontSize, color: textColor, height: 1.55),
    );
  }

  Widget _buildEmpty() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.info_outline, size: 64, color: Colors.grey.shade400),
          const SizedBox(height: 16),
          const Text('Document content could not be extracted.'),
          const SizedBox(height: 8),
          Text(
            'Format: ${widget.docInfo.formatLabel}\n'
            'Records: ${widget.docInfo.numRecords}',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade600),
          ),
          const SizedBox(height: 16),
          TextButton.icon(
            onPressed: () => setState(() => _viewMode = 'info'),
            icon: const Icon(Icons.info),
            label: const Text('View document info'),
          ),
        ],
      ),
    );
  }

  Widget _buildInfo() {
    final items = <String, String>{
      'Title': widget.docInfo.title,
      'File': widget.docInfo.fileName,
      'Format': widget.docInfo.formatLabel,
      'Type/Creator': '${widget.docInfo.type} / ${widget.docInfo.creator}',
      'Version': '0x${widget.docInfo.version.toRadixString(16).padLeft(4, '0')}',
      'Records': '${widget.docInfo.numRecords}',
      'File Size': widget.docInfo.fileSizeLabel,
      if (widget.docInfo.createdAt != null)
        'Created': widget.docInfo.createdAt!.toLocal().toString().split('.').first,
      'Path': widget.docInfo.path,
    };

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Document Information', style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFF1A237E),
                )),
                const Divider(height: 20),
                ...items.entries.map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 100,
                        child: Text(e.key, style: const TextStyle(
                          fontWeight: FontWeight.w600, color: Color(0xFF283593),
                        )),
                      ),
                      Expanded(child: SelectableText(e.value)),
                    ],
                  ),
                )),
              ],
            ),
          ),
        ),
        if (_text != null) ...[
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: () => setState(() => _viewMode = 'text'),
            icon: const Icon(Icons.article),
            label: const Text('Read document'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1A237E),
              foregroundColor: Colors.white,
              minimumSize: const Size.fromHeight(48),
            ),
          ),
        ],
      ],
    );
  }

  Widget _formatBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: const Color(0xFF1A237E),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 10)),
    );
  }
}
