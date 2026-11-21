import SwiftUI

// MARK: - Event

struct EventView: View {
    let eventId: Int
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var event: EventCard?
    @State private var failure: String?
    @State private var askNote = false
    @State private var note = ""
    @State private var showPeople = false

    var body: some View {
        Group {
            if let event {
                content(event)
            } else if let failure {
                EmptyNote(title: "Не получилось загрузить", text: failure)
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .screenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .navigationDestination(isPresented: $showPeople) { PeopleView(eventId: eventId) }
        .sheet(isPresented: $askNote) { noteSheet }
    }

    private func content(_ event: EventCard) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Badge(text: When.label(event.startsAt))
                        Spacer()
                        Badge(text: event.categoryName, fill: Color.ink.opacity(0.35), ink: .white)
                    }
                    Text(event.title)
                        .font(.display(28))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(20)
                .frame(minHeight: (event.image ?? "").isEmpty ? 0 : 220, alignment: .bottom)
                .background(PosterBackground(image: event.image))
                .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))

                HStack(alignment: .top, spacing: 10) {
                    fact("Где", event.place.isEmpty ? "Уточняется" : event.place)
                    fact("Билет", event.price.isEmpty ? "На сайте события" : event.price)
                }
                if !event.address.isEmpty && event.address != event.place {
                    Text(event.address).font(.ui(13)).foregroundStyle(Color.muted)
                }
                if let text = event.description, !text.isEmpty {
                    Text(text).font(.ui(15)).foregroundStyle(Color.ink)
                }

                NavigationLink(value: Route.people(event.id)) {
                    Card {
                        HStack {
                            Text("Кто идёт").font(.ui(17, .heavy)).foregroundStyle(Color.ink)
                            Spacer()
                            if event.going > 0 {
                                Text("Все \(event.going)").font(.ui(14, .heavy)).foregroundStyle(Color.cobaltInk)
                            }
                        }
                        Text(event.looking > 0
                             ? "\(event.looking) " + plural(event.looking, "человек ищет", "человека ищут", "человек ищут") + ", с кем пойти"
                             : "Пока никто не ищет компанию. Будьте первым.")
                            .font(.ui(14, .semibold))
                            .foregroundStyle(Color.ink)
                            .multilineTextAlignment(.leading)
                    }
                }
                .buttonStyle(.plain)

                if let link = event.url, let url = URL(string: link), !link.isEmpty {
                    Button("Билеты и подробности") { openURL(url) }
                        .buttonStyle(BigButtonStyle(fill: .white, ink: .ink, height: 52))
                }
                if event.source == "timepad" {
                    Text("Источник: Timepad").font(.ui(12)).foregroundStyle(Color.muted)
                }
            }
            .padding(20)
        }
        .safeAreaInset(edge: .bottom) { footer(event) }
    }

    private func fact(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.ui(12, .heavy)).foregroundStyle(Color.muted)
            Text(value).font(.ui(15, .bold)).foregroundStyle(Color.ink)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    @ViewBuilder
    private func footer(_ event: EventCard) -> some View {
        let mine = event.myStatus
        if event.started {
            if mine != nil {
                NavigationLink(value: Route.after(event.id)) {
                    Text("С кем хочется увидеться ещё?")
                }
                .buttonStyle(BigButtonStyle())
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.ground)
            }
        } else {
            HStack(spacing: 8) {
                Button(mine == "going" ? "✓ Иду" : "Иду") {
                    Task { await attend(mine == "going" ? "none" : "going", note: "") }
                }
                .buttonStyle(BigButtonStyle(fill: mine == "going" ? .lime : .soft, ink: .ink))
                Button(mine == "looking" ? "✓ Ищу компанию" : "Ищу компанию") {
                    note = event.myNote ?? ""
                    askNote = true
                }
                .buttonStyle(BigButtonStyle(fill: mine == "looking" ? .lime : .ink, ink: mine == "looking" ? .ink : .white))
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.ground)
        }
    }

    private var noteSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Ищу компанию").font(.ui(20, .heavy)).foregroundStyle(Color.ink)
            Text("Вас увидят гости этого события. Напишите пару слов — так проще откликнуться.")
                .font(.ui(15))
                .foregroundStyle(Color.muted)
            Field(title: "Сообщение гостям") {
                TextField("Иду первый раз, хочу компанию из 2–3 человек", text: $note, axis: .vertical)
                    .lineLimit(2...4)
            }
            Button(event?.myStatus == "looking" ? "Сохранить" : "Показать меня гостям") {
                Task {
                    if await attend("looking", note: note) {
                        askNote = false
                        showPeople = true
                    }
                }
            }
            .buttonStyle(BigButtonStyle())
            if event?.myStatus == "looking" {
                Button("Больше не ищу") {
                    Task {
                        await attend("going", note: "")
                        askNote = false
                    }
                }
                .font(.ui(15, .bold))
                .foregroundStyle(Color.danger)
                .frame(maxWidth: .infinity, minHeight: 44)
            }
            Spacer(minLength: 0)
        }
        .padding(20)
        .padding(.top, 8)
        .background(Color.ground)
        .presentationDetents([.medium])
    }

    private func load() async {
        do {
            event = try await API.call("GET", "/events/\(eventId)")
            failure = nil
        } catch is CancellationError {
        } catch {
            if event == nil { failure = error.localizedDescription }
        }
    }

    @discardableResult
    private func attend(_ status: String, note: String) async -> Bool {
        do {
            let _: StatusResponse = try await API.call("POST", "/events/\(eventId)/attend",
                                                       body: ["status": status, "note": String(note.prefix(200))])
            await load()
            if status != "none" { await Nudges.askPermissionIfNeeded() }
            await model.refreshNudges()
            return true
        } catch {
            model.say(error.localizedDescription)
            return false
        }
    }
}

// MARK: - People who look for company

struct PeopleView: View {
    /// nil – everyone for the coming week (the «Люди» tab).
    let eventId: Int?
    @Environment(AppModel.self) private var model
    @State private var people: [Seeker]?
    @State private var event: EventCard?
    @State private var failure: String?
    @State private var reporting: Person?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(subtitle).font(.ui(13, .bold)).foregroundStyle(Color.muted).lineLimit(1)
                    Text("Ищут компанию").font(.display(eventId == nil ? 28 : 24)).foregroundStyle(Color.ink)
                }
                RuleNote()
                if let people {
                    if people.isEmpty {
                        EmptyNote(title: "Пока никого",
                                  text: "Отметьте «Ищу компанию» на странице события, и другие гости увидят вас здесь.")
                    }
                    ForEach(people, id: \.key) { seeker in
                        SeekerCard(seeker: seeker, showEvent: eventId == nil,
                                   invite: { Task { await invite(seeker) } },
                                   report: { reporting = seeker.person })
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
        .toolbar(eventId == nil ? .hidden : .visible, for: .navigationBar)
        .task { await load() }
        .refreshable { await load() }
        .sheet(item: $reporting) { person in
            ReportSheet(person: person) { Task { await load() } }
        }
    }

    private var subtitle: String {
        guard eventId != nil else { return "На этой неделе" }
        guard let event else { return " " }
        return event.title + " · " + When.label(event.startsAt, time: false).lowercased()
    }

    private func load() async {
        do {
            let path = eventId.map { "/events/\($0)/people" } ?? "/people"
            let answer: PeopleResponse = try await API.call("GET", path)
            people = answer.people
            event = answer.event
            failure = nil
        } catch is CancellationError {
        } catch {
            if people == nil { failure = error.localizedDescription }
        }
    }

    private func invite(_ seeker: Seeker) async {
        guard let event = eventId ?? seeker.event?.id else { return }
        do {
            let answer: InviteResponse = try await API.call("POST", "/events/\(event)/invite/\(seeker.id)")
            if let match = answer.matchId {
                model.matchToShow = match
            } else {
                model.say("Если это взаимно, откроется чат")
            }
            await load()
        } catch {
            model.say(error.localizedDescription)
        }
    }
}

struct SeekerCard: View {
    let seeker: Seeker
    let showEvent: Bool
    let invite: () -> Void
    let report: () -> Void

    var body: some View {
        Card {
            if showEvent, let event = seeker.event {
                NavigationLink(value: Route.event(event.id)) {
                    HStack(spacing: 8) {
                        Badge(text: When.label(event.startsAt), fill: .ink, ink: .white)
                        Text(event.title).font(.ui(13, .bold)).foregroundStyle(Color.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
            }
            HStack(alignment: .top, spacing: 12) {
                Avatar(person: seeker.person, size: 56)
                VStack(alignment: .leading, spacing: 6) {
                    Text(seeker.person.title).font(.ui(18, .heavy)).foregroundStyle(Color.ink)
                    let about = seeker.note.isEmpty ? seeker.bio : seeker.note
                    if !about.isEmpty {
                        Text(about).font(.ui(14)).foregroundStyle(Color.ink)
                    }
                }
            }
            if !seeker.interests.isEmpty {
                TagRow(tags: seeker.interests)
            }
            if let match = seeker.matchId {
                NavigationLink(value: Route.chat(match)) { Text("Открыть чат") }
                    .buttonStyle(BigButtonStyle(fill: .lime, ink: .ink, height: 52))
            } else if seeker.invited {
                Text("✓ Вы предложили")
                    .font(.ui(16, .heavy))
                    .foregroundStyle(Color.muted)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Color.soft, in: Capsule())
            } else {
                Button("Пойдём вместе", action: invite)
                    .buttonStyle(BigButtonStyle(fill: .cobalt, height: 52))
            }
            Button("Пожаловаться", action: report)
                .font(.ui(12, .semibold))
                .foregroundStyle(Color.muted)
                .frame(maxWidth: .infinity, minHeight: 28)
        }
    }
}

// MARK: - Mutual match

struct MatchView: View {
    let matchId: Int
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var chat: ChatData?
    @State private var openChat = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.cobalt.ignoresSafeArea()
                if let chat, let me = model.me {
                    let again = chat.kind == "again"
                    VStack(spacing: 28) {
                        Spacer()
                        HStack(spacing: -18) {
                            Avatar(person: me.person, size: 112, shift: me.id % 6 == chat.other.id % 6 ? 1 : 0)
                            Avatar(person: chat.other, size: 112)
                        }
                        VStack(spacing: 10) {
                            Text(again ? "Это взаимно" : "Идёте вместе")
                                .font(.display(34))
                                .foregroundStyle(.white)
                            Text(chat.other.name + (again ? " тоже хочет увидеться ещё.\nНапишите первым."
                                                          : " тоже хочет пойти с вами.\nДоговоритесь, где встретиться."))
                                .font(.ui(17, .semibold))
                                .foregroundStyle(.white)
                                .multilineTextAlignment(.center)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(chat.event.title).font(.ui(15, .heavy)).foregroundStyle(.white)
                            Text(When.label(chat.event.startsAt) + (chat.event.place.isEmpty ? "" : " · " + chat.event.place))
                                .font(.ui(14, .semibold))
                                .foregroundStyle(.white)
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.ink.opacity(0.28), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        Spacer()
                        Button("Открыть чат") { openChat = true }
                            .buttonStyle(BigButtonStyle(fill: .lime, ink: .ink))
                        Button("Позже") { dismiss() }
                            .font(.ui(16, .bold))
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity, minHeight: 48)
                    }
                    .padding(20)
                } else {
                    ProgressView().tint(.white)
                }
            }
            .navigationDestination(isPresented: $openChat) { ChatView(matchId: matchId) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Закрыть") { dismiss() }.foregroundStyle(.white)
                }
            }
            .toolbarBackground(.hidden, for: .navigationBar)
        }
        .task {
            do {
                chat = try await API.call("GET", "/matches/\(matchId)")
            } catch {
                dismiss()
            }
        }
    }
}

// MARK: - After the event

struct AfterView: View {
    let eventId: Int
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var data: AfterResponse?
    @State private var failure: String?
    @State private var busy = false

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 10), count: 3)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let data {
                    Badge(text: When.label(data.event.startsAt, time: false) + " · " + data.event.title, fill: .ink, ink: .white)
                    Text("С кем хочется увидеться ещё?").font(.display(26)).foregroundStyle(Color.ink)
                    Text("Отметьте гостей вечера. Человек узнает об этом, только если отметит вас в ответ.")
                        .font(.ui(15))
                        .foregroundStyle(Color.muted)
                    if data.guests.isEmpty {
                        EmptyNote(title: "Гостей пока нет", text: "Отметки появятся, когда на событии отметится кто-то ещё.")
                    }
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(data.guests) { guest in
                            Button { toggle(guest.id) } label: { tile(guest) }
                                .buttonStyle(.plain)
                                .accessibilityLabel(guest.name)
                                .accessibilityAddTraits(guest.marked ? .isSelected : [])
                        }
                    }
                } else if let failure {
                    EmptyNote(title: "Не получилось загрузить", text: failure)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .padding(20)
        }
        .screenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            if let data, !data.guests.isEmpty {
                VStack(spacing: 8) {
                    Text("Выбрано: \(data.guests.filter(\.marked).count) из \(data.guests.count)")
                        .font(.ui(13, .bold))
                        .foregroundStyle(Color.muted)
                    Button(busy ? "Сохраняем…" : "Готово") { Task { await send(data.guests.filter(\.marked).map(\.id)) } }
                        .buttonStyle(BigButtonStyle())
                        .disabled(busy)
                    Button("Никого не отмечать") { Task { await send([]) } }
                        .font(.ui(15, .bold))
                        .foregroundStyle(Color.muted)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .disabled(busy)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.ground)
            }
        }
        .task { await load() }
    }

    private func tile(_ guest: Guest) -> some View {
        VStack(spacing: 8) {
            Avatar(person: guest.person, size: 56)
            Text(guest.name).font(.ui(13, .heavy)).foregroundStyle(Color.ink).lineLimit(1)
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
            .stroke(guest.marked ? Color.cobalt : Color.clear, lineWidth: 3))
        .overlay(alignment: .topTrailing) {
            if guest.marked {
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(.white)
                    .frame(width: 24, height: 24)
                    .background(Color.cobalt, in: Circle())
                    .padding(8)
            }
        }
    }

    private func toggle(_ id: Int) {
        guard let index = data?.guests.firstIndex(where: { $0.id == id }) else { return }
        data?.guests[index].marked.toggle()
    }

    private func load() async {
        do {
            data = try await API.call("GET", "/events/\(eventId)/after")
        } catch is CancellationError {
        } catch {
            failure = error.localizedDescription
        }
    }

    private func send(_ ids: [Int]) async {
        busy = true
        do {
            let result: AfterResult = try await API.call("POST", "/events/\(eventId)/after", body: ["user_ids": ids])
            if let match = result.matches.first {
                model.matchToShow = match
            } else {
                model.say(ids.isEmpty ? "Хорошо, никого не отмечаем" : "Сохранено. Если отметка взаимная, придёт сообщение.")
            }
            dismiss()
        } catch {
            model.say(error.localizedDescription)
        }
        busy = false
    }
}
