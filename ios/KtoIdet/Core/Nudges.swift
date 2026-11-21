import Foundation
import UserNotifications

/// Local reminders before the weekend: «Пятница! Куда идёте вечером?».
/// They are planned on the phone itself, so no push server is needed. Days when the person
/// already has an event marked until Sunday night are skipped.
enum Nudges {
    private struct Slot {
        let id: String
        let weekday: Int  // Calendar: 1 = Sunday … 7 = Saturday
        let hour: Int
        let minute: Int
        let title: String
        let body: String
    }

    private static let slots = [
        Slot(id: "nudge-thu", weekday: 5, hour: 18, minute: 30, title: "Планы на выходные уже есть?",
             body: "Загляните в афишу: отметьте «Ищу компанию» — и найдётся, с кем пойти."),
        Slot(id: "nudge-fri", weekday: 6, hour: 18, minute: 30, title: "Пятница! Куда идёте вечером?",
             body: "Посмотрите, что идёт сегодня, — может, кто-то уже ищет компанию."),
        Slot(id: "nudge-sat", weekday: 7, hour: 12, minute: 0, title: "Суббота — куда сходить сегодня?",
             body: "Концерты, лекции, прогулки и ужины в Москве. Выберите место и компанию."),
    ]

    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mmxxx"
        return f
    }()

    static func cancel() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: slots.map(\.id))
    }

    /// Asks for permission once, at a moment when reminders make sense to the person.
    static func askPermissionIfNeeded() async {
        let center = UNUserNotificationCenter.current()
        guard await center.notificationSettings().authorizationStatus == .notDetermined else { return }
        _ = try? await center.requestAuthorization(options: [.alert, .sound])
    }

    static func reschedule(enabled: Bool, upcoming: [EventCard]) async {
        cancel()
        guard enabled else { return }
        let center = UNUserNotificationCenter.current()
        let status = await center.notificationSettings().authorizationStatus
        guard status == .authorized || status == .provisional else { return }

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = Config.cityTimeZone
        let now = Date()
        let plans = upcoming.compactMap { parser.date(from: $0.startsAt) }

        for slot in slots {
            var match = DateComponents()
            match.weekday = slot.weekday
            match.hour = slot.hour
            match.minute = slot.minute
            guard let fire = calendar.nextDate(after: now, matching: match, matchingPolicy: .nextTime) else { continue }
            var monday = DateComponents()
            monday.weekday = 2
            monday.hour = 0
            monday.minute = 0
            let weekendEnd = calendar.nextDate(after: fire, matching: monday, matchingPolicy: .nextTime)
                ?? fire.addingTimeInterval(4 * 86_400)
            if plans.contains(where: { $0 > fire.addingTimeInterval(-3 * 3_600) && $0 < weekendEnd }) {
                continue  // already going somewhere this weekend
            }
            let content = UNMutableNotificationContent()
            content.title = slot.title
            content.body = slot.body
            content.sound = .default
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: max(60, fire.timeIntervalSince(now)), repeats: false)
            try? await center.add(UNNotificationRequest(identifier: slot.id, content: content, trigger: trigger))
        }
    }
}
