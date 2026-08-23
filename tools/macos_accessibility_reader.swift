import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

struct Bounds: Encodable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct MetaRecord: Encodable {
    let kind = "meta"
    let app_name: String
    let window_title: String
}

struct TextRecord: Encodable {
    let kind = "text"
    let text: String
    let confidence: Double
    let bbox: Bounds?
    let role: String
    let subrole: String?
    let path: String
    let parent_path: String?
    let depth: Int
    let sequence: Int
}

func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var value: CFTypeRef?
    let error = AXUIElementCopyAttributeValue(element, name as CFString, &value)
    guard error == .success else { return nil }
    return value
}

func stringAttribute(_ element: AXUIElement, _ name: String) -> String? {
    guard let value = attribute(element, name) else { return nil }
    if let text = value as? String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
    return nil
}

func children(_ element: AXUIElement) -> [AXUIElement] {
    guard let value = attribute(element, kAXChildrenAttribute as String),
          let values = value as? [AXUIElement] else {
        return []
    }
    return values
}

func pointAttribute(_ element: AXUIElement, _ name: String) -> CGPoint? {
    guard let value = attribute(element, name), CFGetTypeID(value) == AXValueGetTypeID() else {
        return nil
    }
    var point = CGPoint.zero
    guard AXValueGetValue(value as! AXValue, .cgPoint, &point) else { return nil }
    return point
}

func sizeAttribute(_ element: AXUIElement, _ name: String) -> CGSize? {
    guard let value = attribute(element, name), CFGetTypeID(value) == AXValueGetTypeID() else {
        return nil
    }
    var size = CGSize.zero
    guard AXValueGetValue(value as! AXValue, .cgSize, &size) else { return nil }
    return size
}

func normalizedBounds(_ element: AXUIElement, screen: CGRect) -> Bounds? {
    guard screen.width > 0, screen.height > 0,
          let point = pointAttribute(element, kAXPositionAttribute as String),
          let size = sizeAttribute(element, kAXSizeAttribute as String),
          size.width > 0, size.height > 0 else {
        return nil
    }
    // AX reports the top-left corner in top-left-relative global coordinates;
    // Vision observations use a lower-left origin.  Flip the vertical axis
    // while normalizing to the primary display.
    let x = max(0, min(1, (point.x - screen.minX) / screen.width))
    let topDistance = point.y - screen.minY
    let y = max(0, min(1, (screen.height - topDistance - size.height) / screen.height))
    let width = max(0, min(1 - x, size.width / screen.width))
    let height = max(0, min(1 - y, size.height / screen.height))
    return Bounds(x: x, y: y, width: width, height: height)
}

func textValue(_ element: AXUIElement, role: String) -> String? {
    // Container values (for example a whole AXGroup) duplicate the leaf
    // strings in chat UIs.  Restrict extraction to roles which normally carry
    // user-visible text and leave buttons/menus to OCR when needed.
    let textRoles: Set<String> = [
        kAXStaticTextRole as String,
        kAXTextFieldRole as String,
        kAXTextAreaRole as String,
        kAXComboBoxRole as String,
        kAXCellRole as String,
        "AXLink",
    ]
    guard textRoles.contains(role) else { return nil }
    for name in [
        kAXValueAttribute as String,
        kAXTitleAttribute as String,
        kAXDescriptionAttribute as String,
        kAXSelectedTextAttribute as String,
    ] {
        if let value = stringAttribute(element, name) {
            return value
        }
    }
    return nil
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]

guard AXIsProcessTrusted() else {
    fputs("Accessibility permission not granted\n", stderr)
    exit(2)
}

guard let app = NSWorkspace.shared.frontmostApplication,
      let appName = app.localizedName ?? app.bundleIdentifier,
      !appName.isEmpty else {
    fputs("frontmost application unavailable\n", stderr)
    exit(1)
}

let appElement = AXUIElementCreateApplication(app.processIdentifier)
let windowTitle = stringAttribute(appElement, kAXTitleAttribute as String) ?? ""
let screen = NSScreen.main?.frame ?? CGRect(x: 0, y: 0, width: 1, height: 1)

if let meta = try? encoder.encode(MetaRecord(app_name: appName, window_title: windowTitle)),
   let metaText = String(data: meta, encoding: .utf8) {
    print(metaText)
}

var sequence = 0
var visited = Set<String>()
let maxDepth = 12

func walk(_ element: AXUIElement, depth: Int, path: String, parentPath: String?) {
    guard depth <= maxDepth else { return }
    let identity = "\(path):\(String(describing: element))"
    guard visited.insert(identity).inserted else { return }
    let role = stringAttribute(element, kAXRoleAttribute as String) ?? ""
    let subrole = stringAttribute(element, kAXSubroleAttribute as String)
    if let text = textValue(element, role: role), text.count <= 4000 {
        let record = TextRecord(
            text: text,
            confidence: 1.0,
            bbox: normalizedBounds(element, screen: screen),
            role: role,
            subrole: subrole,
            path: path,
            parent_path: parentPath,
            depth: depth,
            sequence: sequence
        )
        sequence += 1
        if let encoded = try? encoder.encode(record),
           let line = String(data: encoded, encoding: .utf8) {
            print(line)
        }
    }
    for (index, child) in children(element).enumerated() {
        let childPath = "\(path).\(index)"
        walk(child, depth: depth + 1, path: childPath, parentPath: path)
    }
}

walk(appElement, depth: 0, path: "0", parentPath: nil)
