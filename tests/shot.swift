import Foundation
import WebKit
import AppKit

let path = CommandLine.arguments[1]
let outPath = CommandLine.arguments[2]
let url = URL(fileURLWithPath: path)

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

final class D: NSObject, WKNavigationDelegate {
    var wv: WKWebView!
    var out: String
    var fired = false
    init(_ wv: WKWebView, _ out: String) { self.wv = wv; self.out = out; super.init() }
    func webView(_ w: WKWebView, didFinish navigation: WKNavigation!) {
        if fired { return }
        fired = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            self.wv.takeSnapshot(with: WKSnapshotConfiguration()) { img, _ in
                if let img = img,
                   let tiff = img.tiffRepresentation,
                   let rep = NSBitmapImageRep(data: tiff),
                   let png = rep.representation(using: .png, properties: [:]) {
                    try? png.write(to: URL(fileURLWithPath: self.out))
                    print("saved")
                }
                exit(0)
            }
        }
    }
}

let wv = WKWebView(frame: NSRect(x: 0, y: 0, width: 1400, height: 900))
let d = D(wv, outPath)
wv.navigationDelegate = d
wv.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
app.run()
