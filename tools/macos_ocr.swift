import AppKit
import Foundation
import Vision

if CommandLine.arguments.count != 2 {
    fputs("usage: macos_ocr IMAGE_PATH\n", stderr)
    exit(64)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: imageURL),
      let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let cgImage = bitmap.cgImage else {
    fputs("failed to load image\n", stderr)
    exit(65)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("vision ocr failed: \(error)\n", stderr)
    exit(66)
}

let observations = (request.results ?? [])
    .compactMap { observation -> (String, CGRect)? in
        guard let candidate = observation.topCandidates(1).first else {
            return nil
        }
        let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            return nil
        }
        return (text, observation.boundingBox)
    }
    .sorted { left, right in
        let yDelta = abs(left.1.midY - right.1.midY)
        if yDelta > 0.01 {
            return left.1.midY > right.1.midY
        }
        return left.1.minX < right.1.minX
    }

for (text, _) in observations {
    print(text)
}
