import AppKit
import CoreGraphics
import CoreImage
import CoreMedia
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

final class FirstFrameOutput: NSObject, SCStreamOutput {
    private let outputURL: URL
    private let semaphore = DispatchSemaphore(value: 0)
    private var saved = false
    private(set) var failure: String?

    init(outputURL: URL) {
        self.outputURL = outputURL
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, !saved, let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()
        guard let image = context.createCGImage(ciImage, from: ciImage.extent) else {
            failure = "ScreenCaptureKit returned an empty image"
            semaphore.signal()
            return
        }
        do {
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            guard let destination = CGImageDestinationCreateWithURL(
                outputURL as CFURL,
                UTType.png.identifier as CFString,
                1,
                nil
            ) else {
                throw NSError(domain: "wsa.screencapturekit", code: 2, userInfo: [NSLocalizedDescriptionKey: "cannot create PNG destination"])
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else {
                throw NSError(domain: "wsa.screencapturekit", code: 3, userInfo: [NSLocalizedDescriptionKey: "cannot finalize PNG"])
            }
            saved = true
        } catch {
            failure = error.localizedDescription
        }
        semaphore.signal()
    }

    func wait(timeout: TimeInterval) -> Bool {
        semaphore.wait(timeout: .now() + timeout) == .success
    }
}

@main
struct ScreenCaptureKitReader {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments.first == "--status" {
            guard CGPreflightScreenCaptureAccess() else {
                fputs("Screen Recording permission not granted\n", stderr)
                exit(2)
            }
            print("trusted")
            return
        }
        guard let output = arguments.first, !output.isEmpty else {
            fputs("usage: macos_screencapturekit OUTPUT_PATH\n", stderr)
            exit(64)
        }
        guard CGPreflightScreenCaptureAccess() else {
            fputs("Screen Recording permission not granted\n", stderr)
            exit(2)
        }
        do {
            try await captureFrontmostWindow(to: URL(fileURLWithPath: output))
        } catch {
            fputs("\(error.localizedDescription)\n", stderr)
            exit(1)
        }
    }

    static func captureFrontmostWindow(to outputURL: URL) async throws {
        guard let frontmost = NSWorkspace.shared.frontmostApplication else {
            throw NSError(domain: "wsa.screencapturekit", code: 4, userInfo: [NSLocalizedDescriptionKey: "frontmost application unavailable"])
        }
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        let windows = content.windows.filter {
            $0.owningApplication?.processID == frontmost.processIdentifier
                && $0.isOnScreen
                && $0.frame.width > 10
                && $0.frame.height > 10
        }
        guard let window = windows.sorted(by: { lhs, rhs in
            (lhs.frame.width * lhs.frame.height) > (rhs.frame.width * rhs.frame.height)
        }).first else {
            throw NSError(domain: "wsa.screencapturekit", code: 5, userInfo: [NSLocalizedDescriptionKey: "frontmost window unavailable to ScreenCaptureKit"])
        }

        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        configuration.width = max(1, Int(window.frame.width * 2))
        configuration.height = max(1, Int(window.frame.height * 2))
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 30)
        configuration.queueDepth = 3
        configuration.showsCursor = false
        let output = FirstFrameOutput(outputURL: outputURL)
        let stream = SCStream(filter: filter, configuration: configuration, delegate: nil)
        try stream.addStreamOutput(output, type: .screen, sampleHandlerQueue: DispatchQueue(label: "wsa.screencapturekit"))
        try await stream.startCapture()
        defer { Task { try? await stream.stopCapture() } }
        guard output.wait(timeout: 8) else {
            throw NSError(domain: "wsa.screencapturekit", code: 6, userInfo: [NSLocalizedDescriptionKey: "timed out waiting for ScreenCaptureKit frame"])
        }
        if let failure = output.failure {
            throw NSError(domain: "wsa.screencapturekit", code: 7, userInfo: [NSLocalizedDescriptionKey: failure])
        }
    }
}
