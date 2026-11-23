import UIKit

/// The system share sheet, opened from anywhere (links and pictures are prepared asynchronously first).
@MainActor
enum Share {
    static func present(text: String, link: String, image: UIImage? = nil) {
        var items: [Any] = []
        if let image { items.append(image) }
        if let url = URL(string: link) {
            items.append(text + " " + url.absoluteString)
        } else {
            items.append(text)
        }
        present(items)
    }

    static func present(_ items: [Any]) {
        let sheet = UIActivityViewController(activityItems: items, applicationActivities: nil)
        guard let top = topController() else { return }
        sheet.popoverPresentationController?.sourceView = top.view
        top.present(sheet, animated: true)
    }

    /// The picture for an achievement story (made by the server).
    static func picture(_ path: String) async -> UIImage? {
        guard let url = URL(string: path, relativeTo: Config.baseURL),
              let answer = try? await URLSession.shared.data(from: url) else { return nil }
        return UIImage(data: answer.0)
    }

    private static func topController() -> UIViewController? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let window = scenes.flatMap(\.windows).first { $0.isKeyWindow } ?? scenes.first?.windows.first
        var top = window?.rootViewController
        while let next = top?.presentedViewController { top = next }
        return top
    }
}
