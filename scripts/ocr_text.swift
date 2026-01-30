#!/usr/bin/env swift
import Foundation
import Vision
import AppKit

// Usage: ocr_text.swift /path/to/image
// Prints recognized text (best-effort) to stdout.

func die(_ msg: String) -> Never {
  FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
  exit(1)
}

guard CommandLine.arguments.count >= 2 else {
  die("usage: ocr_text.swift <imagePath>")
}

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)

guard let nsImage = NSImage(contentsOf: url) else {
  die("failed to load image: \(path)")
}

guard let tiffData = nsImage.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiffData),
      let cgImage = bitmap.cgImage else {
  die("failed to get CGImage: \(path)")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
// Auto-detect languages; add hints
request.recognitionLanguages = ["zh-Hans", "en-US", "es-ES"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

do {
  try handler.perform([request])
} catch {
  die("vision perform failed: \(error)")
}

guard let results = request.results as? [VNRecognizedTextObservation] else {
  // no results
  exit(0)
}

var lines: [String] = []
lines.reserveCapacity(results.count)

for obs in results {
  if let top = obs.topCandidates(1).first {
    let s = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
    if !s.isEmpty { lines.append(s) }
  }
}

print(lines.joined(separator: "\n"))
