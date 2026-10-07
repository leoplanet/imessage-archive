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
            self.wv.evaluateJavaScript("""
            (() => {
                const input = document.getElementById('search');
                window.__t = {};
                input.value = 'roof';
                input.dispatchEvent(new Event('input'));
                setTimeout(() => {
                    window.__t.afterSearch = document.querySelectorAll('.conv').length;
                    window.__t.firstResult = document.querySelector('.conv .cname')?.textContent;
                    document.querySelector('.conv')?.click();
                    setTimeout(() => {
                        window.__t.afterClick_sidebar = document.querySelectorAll('.conv').length;
                        window.__t.afterClick_thread = document.getElementById('tname').textContent;
                        window.__t.afterClick_rows = document.querySelectorAll('.mrow').length;
                        input.value = '';
                        input.dispatchEvent(new Event('input'));
                        setTimeout(() => {
                            window.__t.afterClear = document.querySelectorAll('.conv').length;
                            window.__t.done = true;
                        }, 400);
                    }, 400);
                }, 400);
                return 1;
            })()
            """, completionHandler: nil)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                self.wv.evaluateJavaScript("window.__t ? JSON.stringify(window.__t) : 'none'") { res, _ in
                    if let s = res as? String { print(s) }
                    exit(0)
                }
            }
        }
    }
}

let wv = WKWebView(frame: NSRect(x: 0, y: 0, width: 1400, height: 900))
let d = D(); d.wv = wv
wv.navigationDelegate = d
wv.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
app.run()
