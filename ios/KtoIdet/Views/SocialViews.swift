import SwiftUI

// MARK: - Friends

struct FriendsView: View {
    @Environment(AppModel.self) private var model
    @State private var data: FriendsResponse?
    @State private var failure: String?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                Text("Друзья").font(.display(28)).foregroundStyle(Color.ink)
                Text("Друзья видят, куда вы идёте, и могут позвать вас в свою компанию. Добавить друга — отправить ему свою ссылку.")
                    .font(.ui(15))
                    .foregroundStyle(Color.muted)
                Button("Позвать друзей") { Task { await model.inviteFriend() } }
                    .buttonStyle(BigButtonStyle())
                if let data {
                    if !data.going.isEmpty {
                        Card {
                            Text("Куда идут друзья").font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                            ForEach(data.going, id: \.self) { item in
                                NavigationLink(value: Route.event(item.event.id)) {
                                    HStack(spacing: 12) {
                                        Avatar(person: item.friend, size: 40)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(item.friend.name + " · " + item.event.title)
                                                .font(.ui(15, .heavy))
                                                .foregroundStyle(Color.ink)
                                                .lineLimit(1)
                                            Text(When.label(item.event.startsAt))
                                                .font(.ui(13, .semibold))
                                                .foregroundStyle(Color.muted)
                                        }
                                        Spacer(minLength: 0)
                                    }
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    Card {
                        Text(data.friends.isEmpty ? "Пока никого" : "Ваши друзья · \(data.friends.count)")
                            .font(.ui(17, .heavy))
                            .foregroundStyle(Color.ink)
                        if data.friends.isEmpty {
                            Text("Отправьте ссылку другу — как только он войдёт по ней, вы станете друзьями.")
                                .font(.ui(14))
                                .foregroundStyle(Color.muted)
                        }
                        ForEach(data.friends) { friend in
                            HStack(spacing: 12) {
                                Avatar(person: friend, size: 40)
                                Text(friend.title).font(.ui(16, .bold)).foregroundStyle(Color.ink)
                                Spacer()
                                Button("Убрать") { Task { await remove(friend) } }
                                    .font(.ui(13, .semibold))
                                    .foregroundStyle(Color.muted)
                            }
                        }
                    }
                } else if let failure {
                    EmptyNote(title: "Не получилось загрузить", text: failure)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .screenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            data = try await API.call("GET", "/friends")
            failure = nil
        } catch is CancellationError {
        } catch {
            if data == nil { failure = error.localizedDescription }
        }
    }

    private func remove(_ friend: Person) async {
        do {
            let _: OkResponse = try await API.call("DELETE", "/friends/\(friend.id)")
            await load()
        } catch {
            model.say(error.localizedDescription)
        }
    }
}

// MARK: - Achievements

struct AchievementTile: View {
    let item: Achievement

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(item.emoji).font(.system(size: 28))
            Text(item.title).font(.ui(13, .heavy)).foregroundStyle(Color.ink).lineLimit(1)
            Text(String(repeating: "★", count: item.level) + String(repeating: "☆", count: max(0, item.levels - item.level)))
                .font(.system(size: 13))
                .foregroundStyle(Color.ink)
            ProgressBar(value: item.progress)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(item.level > 0 ? Color.sky : Color.ground, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .opacity(item.level > 0 ? 1 : 0.55)
    }
}

struct ProgressBar: View {
    let value: Double

    var body: some View {
        GeometryReader { box in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.ink.opacity(0.12))
                Capsule().fill(Color.ink).frame(width: box.size.width * max(0, min(1, value)))
            }
        }
        .frame(height: 6)
    }
}

struct AchievementSheet: View {
    let item: Achievement
    @Environment(\.dismiss) private var dismiss
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(spacing: 6) {
                    Text(item.emoji).font(.system(size: 56))
                    Text(item.level > 0 ? item.title : "Ещё не открыто").font(.ui(22, .heavy)).foregroundStyle(Color.ink)
                    Text(item.next.map { "\(item.value) из \($0) \(item.unit) до «\(item.nextTitle ?? "")»" }
                         ?? "Высший уровень — \(item.value) \(item.unit)")
                        .font(.ui(14, .semibold))
                        .foregroundStyle(Color.muted)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                ForEach(item.steps, id: \.self) { step in
                    HStack {
                        Text(step.done ? "★" : "☆").font(.system(size: 18))
                        Text(step.title).font(.ui(16, .bold)).foregroundStyle(Color.ink)
                        Spacer()
                        Text("от \(step.need)").font(.ui(13, .semibold)).foregroundStyle(Color.muted)
                    }
                    .frame(minHeight: 36)
                }
                Text(item.hint).font(.ui(14)).foregroundStyle(Color.muted)
                if item.level > 0 {
                    Button(busy ? "Готовим картинку…" : "Поделиться") { Task { await share() } }
                        .buttonStyle(BigButtonStyle())
                        .disabled(busy)
                }
            }
            .padding(20)
            .padding(.top, 8)
        }
        .background(Color.ground)
        .presentationDetents([.medium, .large])
    }

    /// A story picture with a medal from the server, plus the personal invite link.
    private func share() async {
        busy = true
        let links: FriendsResponse? = try? await API.call("GET", "/friends")
        let picture = await Share.picture("/ach/\(item.code)-\(item.level).jpg")
        busy = false
        dismiss()
        try? await Task.sleep(for: .milliseconds(500))
        Share.present(text: "\(item.emoji) Моё достижение в «Кто идёт» — «\(item.title)». Хожу на события в Москве с новыми людьми, присоединяйся",
                      link: links?.webLink ?? Config.baseURL.absoluteString, image: picture)
    }
}

struct AchievementsView: View {
    @State private var data: ProgressResponse?
    @State private var chosen: Achievement?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 10), count: 2)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let data {
                    Text("Открыто \(data.achievements.filter { $0.level > 0 }.count) из \(data.achievements.count)")
                        .font(.ui(13, .bold))
                        .foregroundStyle(Color.muted)
                }
                Text("Достижения").font(.display(28)).foregroundStyle(Color.ink)
                if let data {
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(data.achievements) { item in
                            Button { chosen = item } label: { AchievementTile(item: item) }
                                .buttonStyle(.plain)
                        }
                    }
                    Text("Нажмите на достижение, чтобы посмотреть уровни и поделиться.")
                        .font(.ui(13))
                        .foregroundStyle(Color.muted)
                        .frame(maxWidth: .infinity)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .screenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $chosen) { item in AchievementSheet(item: item) }
        .task { data = try? await API.call("GET", "/me/progress") }
    }
}
