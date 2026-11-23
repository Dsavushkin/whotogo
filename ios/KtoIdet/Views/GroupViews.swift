import SwiftUI
import UIKit

// MARK: - Company chat (3–5 people)

struct GroupChatView: View {
    let groupId: Int
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var chat: GroupChat?
    @State private var text = ""
    @State private var failure: String?
    @State private var showMembers = false
    @State private var reporting: Person?
    @State private var confirmLeave = false

    var body: some View {
        VStack(spacing: 0) {
            if let chat {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            NavigationLink(value: Route.event(chat.event.id)) { eventHeader(chat) }
                                .buttonStyle(.plain)
                            note("Мы собрали компанию из тех, кто тоже идёт" + (chat.girlsOnly ? " — только девушки" : "")
                                 + ". Договоритесь, где встретиться")
                            if let captainId = chat.captainId {
                                note(captainId == model.me?.id
                                     ? "⭐ Вы капитан: предложите место встречи и познакомьте всех"
                                     : "⭐ Капитан компании — \(chat.captain?.name ?? ""): встретит всех у входа")
                            }
                            if !chat.promo.isEmpty { dealBox(chat) }
                            IcebreakerNote(text: chat.icebreaker)
                            ForEach(chat.messages) { message in
                                bubble(message, captainId: chat.captainId).id(message.id)
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
                composer(chat)
            } else if let failure {
                EmptyNote(title: "Не получилось загрузить", text: failure)
                Spacer()
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .screenBackground()
        .navigationTitle(chat.map { "Компания из \($0.others.count + 1)" } ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showMembers = true } label: {
                    Image(systemName: "person.3").accessibilityLabel("Участники")
                }
            }
        }
        .sheet(isPresented: $showMembers) { members }
        .sheet(item: $reporting) { person in
            ReportSheet(person: person) { Task { await reload() } }
        }
        .confirmationDialog("Выйти из компании?", isPresented: $confirmLeave, titleVisibility: .visible) {
            Button("Выйти", role: .destructive) { Task { await leave() } }
            Button("Отмена", role: .cancel) {}
        } message: {
            Text("Вы больше не будете в этом чате, и мы не будем собирать вам компанию на это событие.")
        }
        .task { await poll() }
    }

    private func eventHeader(_ chat: GroupChat) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(chat.event.title).font(.ui(14, .heavy)).foregroundStyle(Color.ink)
            Text(When.label(chat.event.startsAt) + (chat.event.place.isEmpty ? "" : " · " + chat.event.place))
                .font(.ui(13, .semibold))
                .foregroundStyle(Color.muted)
            Text("Вы, " + chat.others.map(\.name).joined(separator: ", "))
                .font(.ui(13, .semibold))
                .foregroundStyle(Color.muted)
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private func note(_ text: String) -> some View {
        Text(text)
            .font(.ui(12, .semibold))
            .foregroundStyle(Color.muted)
            .multilineTextAlignment(.center)
            .padding(.vertical, 4)
            .padding(.horizontal, 30)
    }

    /// Group tickets: the promo code is shown only to the company.
    private func dealBox(_ chat: GroupChat) -> some View {
        VStack(spacing: 8) {
            Text("🎟 Скидка для вашей компании: " + chat.deal)
                .font(.ui(13, .bold))
                .foregroundStyle(Color.ink)
                .multilineTextAlignment(.center)
            Button {
                UIPasteboard.general.string = chat.promo
                model.say("Промокод скопирован")
            } label: {
                Text("Промокод \(chat.promo) · скопировать")
                    .font(.ui(13, .heavy))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .frame(height: 36)
                    .background(Color.ink, in: Capsule())
            }
        }
        .padding(12)
        .frame(maxWidth: 320)
        .background(Color.lime, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func bubble(_ message: GroupMessage, captainId: Int?) -> some View {
        HStack {
            if message.mine { Spacer(minLength: 48) }
            VStack(alignment: .leading, spacing: 2) {
                if !message.mine {
                    Text(message.from + (message.fromId == captainId ? " ⭐" : ""))
                        .font(.ui(12, .heavy))
                        .foregroundStyle(Color.cobaltInk)
                }
                Text(message.text)
                    .font(.ui(15))
                    .foregroundStyle(message.mine ? Color.white : Color.ink)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(message.mine ? Color.cobalt : Color.white,
                        in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            if !message.mine { Spacer(minLength: 48) }
        }
    }

    private func composer(_ chat: GroupChat) -> some View {
        VStack(spacing: 8) {
            if chat.messages.isEmpty {
                let quick = ["Всем привет! 👋"] + icebreakerQuestions(chat.icebreaker) + ["Встречаемся у входа за 15 минут?"]
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(quick, id: \.self) { phrase in
                            Chip(title: phrase, selected: false, small: true) { Task { await send(phrase) } }
                        }
                    }
                }
            }
            HStack(spacing: 8) {
                TextField("Сообщение компании", text: $text, axis: .vertical)
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

    private var members: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Компания").font(.ui(20, .heavy)).foregroundStyle(Color.ink)
            if let chat {
                if !chat.full {
                    Button("Позвать друга в компанию") { Task { await inviteFriend() } }
                        .buttonStyle(BigButtonStyle(height: 52))
                }
                ForEach(chat.others) { person in
                    HStack(spacing: 12) {
                        Avatar(person: person, size: 44)
                        Text(person.title + (person.id == chat.captainId ? " ⭐" : ""))
                            .font(.ui(16, .bold))
                            .foregroundStyle(Color.ink)
                        Spacer()
                        Button("Пожаловаться") {
                            showMembers = false
                            Task {
                                try? await Task.sleep(for: .milliseconds(500))  // after the sheet closes
                                reporting = person
                            }
                        }
                        .font(.ui(13, .semibold))
                        .foregroundStyle(Color.muted)
                    }
                }
            }
            Button("Выйти из компании") {
                showMembers = false
                confirmLeave = true
            }
            .font(.ui(15, .bold))
            .foregroundStyle(Color.danger)
            .frame(maxWidth: .infinity, minHeight: 44)
            Spacer(minLength: 0)
        }
        .padding(20)
        .padding(.top, 8)
        .background(Color.ground)
        .presentationDetents([.medium, .large])
    }

    /// Loads the chat, then asks for new messages every few seconds while the screen is open.
    private func poll() async {
        while !Task.isCancelled {
            do {
                if chat == nil {
                    chat = try await API.call("GET", "/groups/\(groupId)")
                } else {
                    let last = chat?.messages.last?.id ?? 0
                    let fresh: GroupChat = try await API.call("GET", "/groups/\(groupId)?after=\(last)")
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

    private func reload() async {
        if let fresh: GroupChat = try? await API.call("GET", "/groups/\(groupId)") { chat = fresh }
    }

    private func append(_ messages: [GroupMessage]) {
        let known = Set(chat?.messages.map(\.id) ?? [])
        chat?.messages.append(contentsOf: messages.filter { !known.contains($0.id) })
    }

    private func send(_ draft: String) async {
        let clean = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let sent: GroupMessage = try await API.call("POST", "/groups/\(groupId)/messages", body: ["text": clean])
            append([sent])
        } catch {
            if text.isEmpty { text = draft }
            model.say(error.localizedDescription)
        }
    }

    private func inviteFriend() async {
        do {
            let links: InviteLinks = try await API.call("GET", "/groups/\(groupId)/invite")
            showMembers = false
            try? await Task.sleep(for: .milliseconds(500))  // the share sheet opens after this one closes
            let title = chat.map { " на «\($0.event.title)»" } ?? ""
            Share.present(text: "Пойдём со мной\(title)? У нас уже собралась компания", link: links.webLink)
        } catch {
            model.say(error.localizedDescription)
        }
    }

    private func leave() async {
        do {
            let _: OkResponse = try await API.call("POST", "/groups/\(groupId)/leave")
            model.say("Вы вышли из компании")
            dismiss()
        } catch {
            model.say(error.localizedDescription)
        }
    }
}
