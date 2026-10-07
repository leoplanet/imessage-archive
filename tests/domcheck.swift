import Foundation
import WebKit
import AppKit

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)
let app = NSApplication.shared
app.setActivationPolicy(.accessory)

final class D: NSObject, WKNavigationDelegate {
    var wv: WKWebView!
    var fired = false
    func webView(_ w: WKWebView, didFinish navigation: WKNavigation!) {
        if fired { return }
        fired = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            let js = """
            (() => {
                const convs = document.querySelectorAll('.conv').length;
                const first = document.querySelector('.conv .cname')?.textContent;
                const firstPrev = document.querySelector('.conv .prev')?.textContent;
                // open first conversation
                document.querySelector('.conv')?.click();
                const rows = document.querySelectorAll('.mrow').length;
                const imgs = document.querySelectorAll('.bubble img').length;
                const days = document.querySelectorAll('.day').length;
                const tname = document.getElementById('tname').textContent;
                const firstBubble = document.querySelector('.bubble')?.textContent?.slice(0, 80);
                return JSON.stringify({convs, first, firstPrev, rows, imgs, days, tname, firstBubble});
            })()
            """
            self.wv.evaluateJavaScript(js) { res, err in
                if case let .some(e) = err { print("ERR: \(e)"); exit(1) }
                if case let .some(s) = res as? String { print(s) }
                exit(0)
            }
        }
    }
}

let wv = WKWebView(frame: NSRect(x: 0, y: 0, width: 1400, height: 900))
let d = D(); d.wv = wv
wv.navigationDelegate = d
wv.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
app.run()
