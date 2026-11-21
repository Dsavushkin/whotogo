import SwiftUI

// MARK: - Chats

struct ChatsView: View {
    @State private var matches: [MatchRow]?
    @State private var past: [EventCard] = []
    @State private var failure: String?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                Text("Чаты").font(.display(28)).foregroundStyle(Color.ink)
                ForEach(past) { event in
                    NavigationLink(value: Route.after(event.id)) {
                        Card(fill: .lime) {
                            Text(When.label(event.startsAt, time: false) + " · " + event.title)
                                .font(.ui(12, .heavy))
                                .foregroundStyle(Color.ink)
                                .lineLimit(1)
                            Text("С кем хочется увидеться ещё?").font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                        }
                    }
                    .buttonStyle(.plain)
                }
                if let matches {
                    if matches.isEmpty && past.isEmpty {
                        EmptyNote(title: "Чатов пока нет",
                                  text: "Чат открывается, когда вы и другой гость оба нажали «Пойдём вместе».")
                    }
                    ForEach(matches) { match in
                        NavigationLink(value: Route.chat(match.id)) { row(match) }
                            .buttonStyle(.plain)
                    }
                } else if let failure {
                    EmptyNote(title: "Не получилось загрузить", text: failure)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .task { await load() }
        .refreshable { await load() }
    }

    private func row(_ match: MatchRow) -> some View {
        HStack(spacing: 14) {
            Avatar(person: match.other, size: 56)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(match.other.name).font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                    Spacer()
                    Text(When.label(match.at, time: false)).font(.ui(12, .bold)).foregroundStyle(Color.muted)
                }
                Text(match.last.isEmpty ? match.event.title : (match.lastMine ? "Вы: " : "") + match.last)
                    .font(.ui(13, .semibold))
                    .foregroundStyle(Color.muted)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private func load() async {
        do {
            let list: MatchesResponse = try await API.call("GET", "/matches")
            let mine: MyEvents = try await API.call("GET", "/my/events")
            matches = list.matches
            past = mine.past
            failure = nil
        } catch is CancellationError {
        } catch {
            if matches == nil { failure = error.localizedDescription }
        }
    }
}

// MARK: - One chat

struct ChatView: View {
    let matchId: Int
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var chat: ChatData?
    @State private var text = ""
    @State private var failure: String?
    @State private var reporting: Person?

    private let quick = ["Привет! Где встретимся?", "У входа за 15 минут до начала", "Я уже внутри"]

    var body: some View {
        VStack(spacing: 0) {
            if let chat {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(chat.event.title).font(.ui(14, .heavy)).foregroundStyle(Color.ink)
                                Text(When.label(chat.event.startsAt) + (chat.event.place.isEmpty ? "" : " · " + chat.event.place))
                                    .font(.ui(13, .semibold))
                                    .foregroundStyle(Color.muted)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))

                            Text(chat.kind == "again" ? "Чат открылся, потому что вы отметили друг друга после вечера"
                                                      : "Чат открылся, потому что вы оба захотели пойти вместе")
                                .font(.ui(12, .semibold))
                                .foregroundStyle(Color.muted)
                                .multilineTextAlignment(.center)
                                .padding(.vertical, 6)
                                .padding(.horizontal, 40)

                            ForEach(chat.messages) { message in
                                bubble(message).id(message.id)
                            }
                        }
                        .padding(16)
                    }
                    .onChange(of: chat.messages.count) { _, _ in
                        if let last = chat.messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                    .onAppear {
                        if let last = chat.messages.last { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
                composer(showQuick: chat.messages.isEmpty)
            } else if let failure {
                EmptyNote(title: "Не получилось загрузить", text: failure)
                Spacer()
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .screenBackground()
        .navigationTitle(chat?.other.name ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Пожаловаться и скрыть", role: .destructive) { reporting = chat?.other }
                } label: {
                    Image(systemName: "ellipsis").accessibilityLabel("Ещё")
                }
            }
        }
        .sheet(item: $reporting) { person in
            ReportSheet(person: person) { dismiss() }
        }
        .task { await poll() }
    }

    private func bubble(_ message: ChatMessage) -> some View {
        HStack {
            if message.mine { Spacer(minLength: 48) }
            Text(message.text)
                .font(.ui(15))
                .foregroundStyle(message.mine ? Color.white : Color.ink)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(message.mine ? Color.cobalt : Color.white,
                            in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            if !message.mine { Spacer(minLength: 48) }
        }
    }

    private func composer(showQuick: Bool) -> some View {
        VStack(spacing: 8) {
            if showQuick {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(quick, id: \.self) { phrase in
                            Chip(title: phrase, selected: false, small: true) { Task { await send(phrase) } }
                        }
                    }
                }
            }
            HStack(spacing: 8) {
                TextField("Сообщение", text: $text, axis: .vertical)
                    .lineLimit(1...4)
                    .font(.ui(15, .semibold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                Button {
                    let draft = text
                    text = ""
                    Task { await send(draft) }
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 18, weight: .heavy))
                        .foregroundStyle(.white)
                        .frame(width: 52, height: 52)
                        .background(Color.ink, in: Circle())
                }
                .accessibilityLabel("Отправить")
                .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color.ground)
    }

    /// Loads the chat, then asks for new messages every few seconds while the screen is open.
    private func poll() async {
        while !Task.isCancelled {
            do {
                if chat == nil {
                    chat = try await API.call("GET", "/matches/\(matchId)")
                } else {
                    let last = chat?.messages.last?.id ?? 0
                    let fresh: ChatData = try await API.call("GET", "/matches/\(matchId)?after=\(last)")
                    append(fresh.messages)
                }
                failure = nil
            } catch is CancellationError {
                return
            } catch {
                if chat == nil { failure = error.localizedDescription }
            }
            try? await Task.sleep(for: .seconds(4))
        }
    }

    private func append(_ messages: [ChatMessage]) {
        let known = Set(chat?.messages.map(\.id) ?? [])
        chat?.messages.append(contentsOf: messages.filter { !known.contains($0.id) })
    }

    private func send(_ draft: String) async {
        let clean = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let sent: ChatMessage = try await API.call("POST", "/matches/\(matchId)/messages", body: ["text": clean])
            append([sent])
        } catch {
            if text.isEmpty { text = draft }
            model.say(error.localizedDescription)
        }
    }
}

// MARK: - Report

struct ReportSheet: View {
    let person: Person
    let done: () -> Void
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var reason = ""
    @State private var busy = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Пожаловаться").font(.ui(20, .heavy)).foregroundStyle(Color.ink)
            Text("Этот человек больше не увидит вас, а вы — его. Жалобу прочитает команда.")
                .font(.ui(15))
                .foregroundStyle(Color.muted)
            Field(title: "Что случилось") {
                TextField("Необязательно", text: $reason, axis: .vertical).lineLimit(2...4)
            }
            Button(busy ? "Отправляем…" : "Скрыть и пожаловаться") { Task { await send() } }
                .buttonStyle(BigButtonStyle())
                .disabled(busy)
            Button("Отмена") { dismiss() }
                .font(.ui(15, .bold))
                .foregroundStyle(Color.ink)
                .frame(maxWidth: .infinity, minHeight: 44)
            Spacer(minLength: 0)
        }
        .padding(20)
        .padding(.top, 8)
        .background(Color.ground)
        .presentationDetents([.medium])
    }

    private func send() async {
        busy = true
        do {
            let _: OkResponse = try await API.call("POST", "/users/\(person.id)/report",
                                                   body: ["reason": String(reason.prefix(500)), "block": true])
            model.say("Скрыли. Спасибо, что сообщили.")
            dismiss()
            done()
        } catch {
            model.say(error.localizedDescription)
        }
        busy = false
    }
}

// MARK: - Profile

struct ProfileView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var upcoming: [EventCard] = []
    @State private var editing = false
    @State private var confirmDelete = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Профиль").font(.display(28)).foregroundStyle(Color.ink)
                if let me = model.me {
                    Card {
                        HStack(alignment: .top, spacing: 14) {
                            Avatar(person: me.person, size: 56)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(me.person.title).font(.ui(20, .heavy)).foregroundStyle(Color.ink)
                                if !me.bio.isEmpty {
                                    Text(me.bio).font(.ui(14)).foregroundStyle(Color.ink)
                                }
                            }
                        }
                        if !me.interests.isEmpty { TagRow(tags: me.interests) }
                        Button("Изменить") { editing = true }
                            .buttonStyle(BigButtonStyle(fill: .soft, ink: .ink, height: 52))
                    }
                }
                Card {
                    Text("Мои события").font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                    if upcoming.isEmpty {
                        Text("Отметьте «Иду» или «Ищу компанию» на событии, и оно появится здесь.")
                            .font(.ui(14))
                            .foregroundStyle(Color.muted)
                    }
                    ForEach(upcoming) { event in
                        NavigationLink(value: Route.event(event.id)) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(event.title).font(.ui(15, .heavy)).foregroundStyle(Color.ink).lineLimit(1)
                                Text(When.label(event.startsAt) + " · " + (event.myStatus == "looking" ? "ищу компанию" : "иду"))
                                    .font(.ui(13, .semibold))
                                    .foregroundStyle(Color.muted)
                            }
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                    }
                }
                Card {
                    Text("Проводите вечера?").font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                    Text("Добавьте своё событие в афишу и узнайте, сколько гостей нашли компанию. Кабинет организатора работает в Telegram.")
                        .font(.ui(14))
                        .foregroundStyle(Color.muted)
                    Button("Открыть бота") {
                        if let url = URL(string: "https://t.me/\(Config.bot)") { openURL(url) }
                    }
                    .buttonStyle(BigButtonStyle(fill: .soft, ink: .ink, height: 52))
                }
                Text(markdown("[Соглашение](\(Config.baseURL.absoluteString)/terms) · [Конфиденциальность](\(Config.baseURL.absoluteString)/privacy)"))
                    .font(.ui(13, .bold))
                    .frame(maxWidth: .infinity)
                Button("Выйти") { Task { await model.signOut() } }
                    .font(.ui(15, .bold))
                    .foregroundStyle(Color.ink)
                    .frame(maxWidth: .infinity, minHeight: 44)
                Button("Удалить аккаунт") { confirmDelete = true }
                    .font(.ui(15, .bold))
                    .foregroundStyle(Color.danger)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .task { await load() }
        .sheet(isPresented: $editing) {
            ProfileFormView(first: false).environment(model)
        }
        .confirmationDialog("Удалить аккаунт?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Удалить всё", role: .destructive) {
                Task {
                    do { try await model.deleteAccount() } catch { model.say(error.localizedDescription) }
                }
            }
            Button("Отмена", role: .cancel) {}
        } message: {
            Text("Профиль, отметки и переписка удалятся без возможности восстановления.")
        }
    }

    private func load() async {
        if let mine: MyEvents = try? await API.call("GET", "/my/events") {
            upcoming = mine.upcoming
        }
    }
}
