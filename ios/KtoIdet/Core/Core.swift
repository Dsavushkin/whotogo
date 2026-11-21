import Foundation
import Observation
import Security

// MARK: - Settings

enum Config {
    /// Server address. Change here when the service moves to its own domain.
    static let baseURL = URL(string: "https://111-88-80-60.sslip.io")!
    static let bot = "whotogobot"
    static let cityTimeZone = TimeZone(identifier: "Europe/Moscow")!
}

// MARK: - Data from the server

struct Person: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let age: Int?
    let bio: String
    let interests: [String]

    var title: String { age.map { "\(name), \($0)" } ?? name }
    var initial: String { String(name.trimmingCharacters(in: .whitespaces).prefix(1)).uppercased() }
}

struct Me: Codable, Hashable {
    let id: Int
    var name: String
    var age: Int?
    var bio: String
    var interests: [String]
    var adultOk: Bool
    var isOrganizer: Bool
    var isAdmin: Bool
    var nudges: Bool?

    var person: Person { Person(id: id, name: name, age: age, bio: bio, interests: interests) }
}

struct EventCard: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let category: String
    let categoryName: String
    let startsAt: String
    let place: String
    let address: String
    let price: String
    let going: Int
    let looking: Int
    let started: Bool
    var image: String?
    // Only on the event page and in «my events».
    var description: String?
    var url: String?
    var source: String?
    var myStatus: String?
    var myNote: String?
    var faces: [String]?
}

struct Seeker: Codable, Hashable {
    let id: Int
    let name: String
    let age: Int?
    let bio: String
    let interests: [String]
    let note: String
    var invited: Bool
    var matchId: Int?
    let event: EventCard?

    var person: Person { Person(id: id, name: name, age: age, bio: bio, interests: interests) }
    var key: String { "\(id)-\(event?.id ?? 0)" }
}

struct Guest: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let age: Int?
    let bio: String
    let interests: [String]
    var marked: Bool

    var person: Person { Person(id: id, name: name, age: age, bio: bio, interests: interests) }
}

struct MatchRow: Codable, Identifiable, Hashable {
    let id: Int
    let kind: String
    let other: Person
    let event: EventCard
    let last: String
    let lastMine: Bool
    let at: String
}

struct ChatMessage: Codable, Identifiable, Hashable {
    let id: Int
    let mine: Bool
    let text: String
    let at: String
}

struct ChatData: Codable, Hashable {
    let id: Int
    let kind: String
    let other: Person
    let event: EventCard
    var messages: [ChatMessage]
}

struct EventsResponse: Codable {
    let events: [EventCard]
    let categories: [String: String]
}

struct PeopleResponse: Codable {
    let people: [Seeker]
    let event: EventCard?
}

struct AfterResponse: Codable {
    let event: EventCard
    var guests: [Guest]
}

struct InviteResponse: Codable { let matchId: Int? }
struct AfterResult: Codable { let marked: Int; let matches: [Int] }
struct MatchesResponse: Codable { let matches: [MatchRow] }
struct MyEvents: Codable { let upcoming: [EventCard]; let past: [EventCard] }
struct TokenResponse: Codable { let token: String }
struct StatusResponse: Codable { let myStatus: String? }
struct OkResponse: Codable { let ok: Bool? }

// MARK: - Keychain (the sign-in token)

enum Keychain {
    private static let account = "session"
    private static let service = "com.whotogo.app"

    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    static var token: String? {
        get {
            var q = query
            q[kSecReturnData as String] = true
            q[kSecMatchLimit as String] = kSecMatchLimitOne
            var item: CFTypeRef?
            guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
            return String(data: data, encoding: .utf8)
        }
        set {
            SecItemDelete(query as CFDictionary)
            guard let value = newValue, let data = value.data(using: .utf8) else { return }
            var q = query
            q[kSecValueData as String] = data
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(q as CFDictionary, nil)
        }
    }
}

// MARK: - Requests

struct APIError: LocalizedError {
    let message: String
    let status: Int
    var errorDescription: String? { message }
}

enum API {
    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    static func call<T: Decodable>(_ method: String, _ path: String, body: [String: Any]? = nil) async throws -> T {
        guard let url = URL(string: "/api" + path, relativeTo: Config.baseURL) else {
            throw APIError(message: "Неверный адрес запроса.", status: 0)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = Keychain.token {
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            throw APIError(message: "Нет связи. Проверьте интернет и попробуйте ещё раз.", status: 0)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let detail = object?["detail"] as? String
            throw APIError(message: detail ?? "Проверьте, что всё заполнено верно.", status: status)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(message: "Сервер ответил непонятно. Обновите приложение.", status: status)
        }
    }
}

// MARK: - Dates

enum When {
    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = Config.cityTimeZone
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let labelFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "ru_RU")
        f.timeZone = Config.cityTimeZone
        f.dateFormat = "EE, d MMMM"
        return f
    }()

    private static func cityDay(_ shift: Int) -> String {
        dayFormatter.string(from: Date().addingTimeInterval(Double(shift) * 86_400))
    }

    /// "2026-11-21T20:00+03:00" → "Сегодня · 20:00". The string is already in city time.
    static func label(_ iso: String, time: Bool = true) -> String {
        guard iso.count >= 16 else { return "" }
        let day = String(iso.prefix(10))
        let clock = String(iso.dropFirst(11).prefix(5))
        var text: String
        if day == cityDay(0) {
            text = "Сегодня"
        } else if day == cityDay(1) {
            text = "Завтра"
        } else if day == cityDay(-1) {
            text = "Вчера"
        } else if let date = dayFormatter.date(from: day) {
            text = labelFormatter.string(from: date)
        } else {
            text = day
        }
        return time ? text + " · " + clock : text
    }
}

func plural(_ n: Int, _ one: String, _ few: String, _ many: String) -> String {
    let a = abs(n) % 100, b = a % 10
    if a > 10 && a < 20 { return many }
    if b == 1 { return one }
    if b > 1 && b < 5 { return few }
    return many
}

// MARK: - App state

@MainActor
@Observable
final class AppModel {
    enum Phase { case loading, signedOut, profile, ready, offline }

    static let shared = AppModel()

    var phase: Phase = .loading
    var me: Me?
    var tab = 0
    /// Guests can browse the afisha; everything personal asks to sign in first.
    var showLogin = false
    var isGuest: Bool { me == nil }
    /// A fresh mutual match to celebrate (shown over everything).
    var matchToShow: Int?
    var toast: String?

    func start() async {
        guard Keychain.token != nil else { phase = .signedOut; return }
        do {
            let me: Me = try await API.call("GET", "/me")
            apply(me)
        } catch let error as APIError where error.status == 401 {
            Keychain.token = nil
            phase = .signedOut
        } catch {
            phase = .offline
        }
    }

    func signIn(code: String) async throws {
        let answer: TokenResponse = try await API.call("POST", "/auth/code", body: ["code": code])
        Keychain.token = answer.token
        let me: Me = try await API.call("GET", "/me")
        apply(me)
    }

    func signIn(email: String, password: String, signup: Bool) async throws {
        let answer: TokenResponse = try await API.call("POST", signup ? "/auth/register" : "/auth/login",
                                                       body: ["email": email, "password": password])
        Keychain.token = answer.token
        let me: Me = try await API.call("GET", "/me")
        apply(me)
    }

    func saveProfile(name: String, age: Int, bio: String, interests: [String]) async throws {
        let me: Me = try await API.call("PUT", "/me", body: [
            "name": name, "age": age, "bio": bio, "interests": interests, "adult_ok": true,
        ])
        apply(me)
    }

    /// «Куда идёте на выходных?» reminders on this iPhone.
    func refreshNudges() async {
        guard let me, me.adultOk else { return }
        let mine: MyEvents? = try? await API.call("GET", "/my/events")
        await Nudges.reschedule(enabled: me.nudges ?? true, upcoming: mine?.upcoming ?? [])
    }

    func setNudges(_ on: Bool) async {
        if on { await Nudges.askPermissionIfNeeded() }
        if let updated: Me = try? await API.call("PUT", "/me/settings", body: ["nudges": on]) {
            me = updated
        }
        await refreshNudges()
    }

    func signOut() async {
        Nudges.cancel()
        let _: OkResponse? = try? await API.call("POST", "/auth/logout")
        Keychain.token = nil
        me = nil
        tab = 0
        phase = .signedOut
    }

    func deleteAccount() async throws {
        let _: OkResponse = try await API.call("DELETE", "/me")
        Nudges.cancel()
        Keychain.token = nil
        me = nil
        tab = 0
        phase = .signedOut
    }

    func say(_ text: String) {
        toast = text
        Task {
            try? await Task.sleep(for: .seconds(3))
            if toast == text { toast = nil }
        }
    }

    private func apply(_ me: Me) {
        self.me = me
        showLogin = false
        phase = me.adultOk ? .ready : .profile
    }
}

/// Text with links written as Markdown.
func markdown(_ text: String) -> AttributedString {
    (try? AttributedString(markdown: text)) ?? AttributedString(text)
}
