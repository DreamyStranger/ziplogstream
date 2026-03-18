# Architecture

## Goal
ziplogstream streams decoded text lines from files inside ZIP archives without extracting them to disk or loading the full file into memory.

## Package Layout

### archive/
- validators.py
  - normalizes ZIP paths
  - validates archive inputs
- member_resolution.py
  - deterministic member selection
  - resolves target to a single member

### streaming/
- line_streamer.py
  - public orchestration layer
  - opens ZIP and delegates reading
- buffered_line_reader.py
  - chunked binary-to-text line iteration
  - handles CRLF normalization
  - handles oversized lines

### config.py
- immutable LineStreamerConfig
- validates streaming parameters

### errors.py
- public exception hierarchy

### __init__.py
- defines public exports

## Design Boundaries
- archive logic is isolated in archive/
- streaming logic is isolated in streaming/
- LineStreamer coordinates but does not implement heavy logic
- BufferedLineReader is ZIP-agnostic
- config validation is eager and strict

## Runtime Flow
1. Normalize ZIP path
2. Validate ZIP input
3. Open archive
4. Resolve member name
5. Open member stream
6. Iterate decoded lines

## Public API
- LineStreamer
- LineStreamerConfig
- default_zip_member_resolver
- package exception classes

Internal modules are not part of the public API unless explicitly exported.