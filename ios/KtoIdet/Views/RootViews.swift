import SwiftUI

@main
struct KtoIdetApp: App {
    @State private var model = AppModel.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .preferredColorScheme(.light)
                .tint(.cobalt)
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.ground.ignoresSafeArea()
            switch model.phase {
            case .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .signedOut:
                LoginView()
            case .profile:
                ProfileFormView(first: true)
            case .ready:
                MainTabs()
            case .offline:
                VStack(spacing: 12) {
                    EmptyNote(title: "Нет связи", text: "Проверьте интернет и попробуйте ещё раз.")
                    Button("Повторить") {
                        model.phase = .loading
                        Task { await model.start() }
                    }
                    .buttonStyle(BigButtonStyle(height: 52))
                    .padding(.horizontal, 60)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if let toast = model.toast {
                Text(toast)
                    .font(.ui(14, .bold))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 12)
                    .background(Color.ink, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .padding(.horizontal, 24)
                    .padding(.bottom, 96)
                    .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.2), value: model.toast)
        .task { await model.start() }
        .fullScreenCover(item: Binding(
            get: { model.matchToShow.map(MatchID.init) },
            set: { model.matchToShow = $0?.id }
        )) { match in
            MatchView(matchId: match.id)
                .environment(model)
        }
    }
}

struct MatchID: Identifiable { let id: Int }

enum Route: Hashable {
    case event(Int)
    case people(Int)
    case chat(Int)
    case after(Int)
}

extension View {
    /// Destinations shared by every tab.
    func appRoutes() -> some View {
        navigationDestination(for: Route.self) { route in
            switch route {
            case .event(let id): EventView(eventId: id)
            case .people(let id): PeopleView(eventId: id)
            case .chat(let id): ChatView(matchId: id)
            case .after(let id): AfterView(eventId: id)
            }
        }
    }

    func screenBackground() -> some View {
        background(Color.ground.ignoresSafeArea())
            .toolbarBackground(Color.ground, for: .navigationBar)
    }
}

struct MainTabs: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        TabView(selection: $model.tab) {
            NavigationStack { AfishaView().appRoutes() }
                .tabItem { Label("Афиша", systemImage: "calendar") }
                .tag(0)
            NavigationStack { PeopleView(eventId: nil).appRoutes() }
                .tabItem { Label("Люди", systemImage: "person.2") }
                .tag(1)
            NavigationStack { ChatsView().appRoutes() }
                .tabItem { Label("Чаты", systemImage: "bubble.left.and.bubble.right") }
                .tag(2)
            NavigationStack { ProfileView().appRoutes() }
                .tabItem { Label("Профиль", systemImage: "person.crop.circle") }
                .tag(3)
        }
        .tint(.ink)
    }
}

// MARK: - Sign in

struct LoginView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var signup = false
    @State private var email = ""
    @State private var password = ""
    @State private var code = ""
    @State private var useCode = false
    @State private var busy = false
    @State private var failure: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Афиша и компания на вечер")
                    .font(.ui(13, .bold))
                    .foregroundStyle(Color.muted)
                Text("Кто идёт")
                    .font(.display(40))
                    .foregroundStyle(Color.ink)
                Text("Выберите событие, отметьте «Ищу компанию» и посмотрите, кто ещё идёт. Чат откроется, только если интерес взаимный.")
                    .font(.ui(16))
                    .foregroundStyle(Color.muted)

                if useCode {
                    Text("Откройте бота @\(Config.bot) в Telegram: он пришлёт код из шести цифр.")
                        .font(.ui(15))
                        .foregroundStyle(Color.ink)
                    Button("Получить код в Telegram") {
                        if let url = URL(string: "https://t.me/\(Config.bot)?start=login") { openURL(url) }
                    }
                    .buttonStyle(BigButtonStyle(fill: .cobalt, height: 52))
                    Field(title: "Код из бота") {
                        TextField("000000", text: $code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .onChange(of: code) { _, value in
                                code = String(value.filter(\.isNumber).prefix(6))
                            }
                    }
                } else {
                    Field(title: "Почта") {
                        TextField("you@example.com", text: $email)
                            .keyboardType(.emailAddress)
                            .textContentType(.username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                    Field(title: "Пароль") {
                        SecureField(signup ? "Не короче 8 символов" : "Ваш пароль", text: $password)
                            .textContentType(signup ? .newPassword : .password)
                    }
                }

                if let failure {
                    Text(failure).font(.ui(14, .bold)).foregroundStyle(Color.danger)
                }

                Button(busy ? "Входим…" : (signup && !useCode ? "Создать аккаунт" : "Войти")) { Task { await submit() } }
                    .buttonStyle(BigButtonStyle())
                    .disabled(busy)

                if !useCode {
                    Button(signup ? "У меня уже есть аккаунт" : "Создать аккаунт") {
                        signup.toggle()
                        failure = nil
                    }
                    .font(.ui(15, .bold))
                    .foregroundStyle(Color.ink)
                    .frame(maxWidth: .infinity, minHeight: 44)
                }
                Button(useCode ? "Войти по почте" : "Войти через Telegram") {
                    useCode.toggle()
                    failure = nil
                }
                .font(.ui(14, .bold))
                .foregroundStyle(Color.muted)
                .frame(maxWidth: .infinity, minHeight: 44)

                if signup && !useCode {
                    Text(markdown("Создавая аккаунт, вы принимаете [соглашение](\(Config.baseURL.absoluteString)/terms) и [политику конфиденциальности](\(Config.baseURL.absoluteString)/privacy)."))
                        .font(.ui(13))
                        .foregroundStyle(Color.muted)
                }
            }
            .padding(20)
            .padding(.top, 24)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func submit() async {
        failure = nil
        let mail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if useCode {
            guard code.count == 6 else { failure = "Введите шесть цифр из сообщения бота."; return }
        } else {
            guard mail.contains("@"), mail.contains(".") else { failure = "Проверьте адрес почты."; return }
            guard password.count >= 8 else {
                failure = signup ? "Пароль должен быть не короче 8 символов." : "Почта или пароль не подходят."
                return
            }
        }
        busy = true
        do {
            if useCode {
                try await model.signIn(code: code)
            } else {
                try await model.signIn(email: mail, password: password, signup: signup)
            }
        } catch {
            failure = error.localizedDescription
        }
        busy = false
    }
}

// MARK: - Profile form

struct ProfileFormView: View {
    static let interests = ["музыка", "кино", "театр", "настолки", "бары", "еда", "вино", "прогулки", "спорт", "бег",
                            "йога", "танцы", "искусство", "книги", "путешествия", "фотография", "стендап", "наука",
                            "языки", "игры"]

    let first: Bool
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var age = ""
    @State private var bio = ""
    @State private var chosen: [String] = []
    @State private var adult = false
    @State private var busy = false
    @State private var failure: String?
    @State private var filled = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(first ? "Пара слов о вас" : "Профиль")
                    .font(.display(28))
                    .foregroundStyle(Color.ink)
                if first {
                    Text("Это увидят гости событий, когда вы ищете компанию. Фото не нужно.")
                        .font(.ui(15))
                        .foregroundStyle(Color.muted)
                }
                Field(title: "Имя") {
                    TextField("Как вас зовут", text: $name).textContentType(.givenName)
                }
                Field(title: "Возраст") {
                    TextField("Например, 27", text: $age).keyboardType(.numberPad)
                }
                Field(title: "О себе") {
                    TextField("Что любите, с кем хотите пойти", text: $bio, axis: .vertical).lineLimit(3...6)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text("Интересы, до пяти").font(.ui(13, .bold)).foregroundStyle(Color.muted)
                    FlowLayout(spacing: 8) {
                        ForEach(Self.interests, id: \.self) { tag in
                            Chip(title: tag, selected: chosen.contains(tag), small: true) { toggle(tag) }
                        }
                    }
                }
                if first {
                    Toggle(isOn: $adult) {
                        Text(markdown("Мне есть 18 лет. Принимаю [пользовательское соглашение](\(Config.baseURL.absoluteString)/terms) и [политику конфиденциальности](\(Config.baseURL.absoluteString)/privacy)."))
                            .font(.ui(14, .semibold))
                            .foregroundStyle(Color.ink)
                    }
                    .tint(.cobalt)
                }
                if let failure {
                    Text(failure).font(.ui(14, .bold)).foregroundStyle(Color.danger)
                }
                Button(busy ? "Сохраняем…" : (first ? "Открыть афишу" : "Сохранить")) { Task { await save() } }
                    .buttonStyle(BigButtonStyle())
                    .disabled(busy)
                if first {
                    Button("Выйти") { Task { await model.signOut() } }
                        .font(.ui(15, .bold))
                        .foregroundStyle(Color.muted)
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
            }
            .padding(20)
        }
        .scrollDismissesKeyboard(.interactively)
        .screenBackground()
        .onAppear(perform: fill)
    }

    private func fill() {
        guard !filled, let me = model.me else { return }
        filled = true
        name = me.adultOk ? me.name : (me.name.hasPrefix("User ") ? "" : me.name)
        age = me.age.map { String($0) } ?? ""
        bio = me.bio
        chosen = me.interests
    }

    private func toggle(_ tag: String) {
        if let index = chosen.firstIndex(of: tag) {
            chosen.remove(at: index)
        } else if chosen.count < 5 {
            chosen.append(tag)
        } else {
            model.say("Можно выбрать до пяти")
        }
    }

    private func save() async {
        let cleanName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanName.isEmpty else { failure = "Напишите, как вас зовут."; return }
        guard let years = Int(age), years >= 18 else { failure = "Сервис только для тех, кому есть 18 лет."; return }
        guard years <= 99 else { failure = "Проверьте возраст."; return }
        if first && !adult { failure = "Подтвердите возраст и согласие с правилами."; return }
        busy = true
        failure = nil
        do {
            try await model.saveProfile(name: cleanName, age: years, bio: bio, interests: chosen)
            if !first {
                model.say("Сохранено")
                dismiss()
            }
        } catch {
            failure = error.localizedDescription
        }
        busy = false
    }
}

// MARK: - Afisha

struct AfishaView: View {
    @State private var day = "today"
    @State private var category = ""
    @State private var data: EventsResponse?
    @State private var failure: String?

    private let days = [("today", "Сегодня"), ("tomorrow", "Завтра"), ("weekend", "Выходные"), ("week", "Неделя")]
    private let titles = ["today": "Куда сегодня?", "tomorrow": "Куда завтра?", "weekend": "Куда на выходных?",
                          "week": "Куда на неделе?"]

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Москва").font(.ui(13, .bold)).foregroundStyle(Color.muted)
                    Text(titles[day] ?? "Афиша").font(.display(28)).foregroundStyle(Color.ink)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(days, id: \.0) { item in
                            Chip(title: item.1, selected: day == item.0) { day = item.0 }
                        }
                    }
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        Chip(title: "Всё", selected: category.isEmpty, small: true) { category = "" }
                        ForEach(categories, id: \.0) { item in
                            Chip(title: item.1, selected: category == item.0, small: true) { category = item.0 }
                        }
                    }
                }
                if let data {
                    if data.events.isEmpty {
                        EmptyNote(title: "Пока пусто", text: "На эти даты событий нет. Посмотрите другие дни.")
                    }
                    ForEach(Array(data.events.enumerated()), id: \.element.id) { index, event in
                        NavigationLink(value: Route.event(event.id)) {
                            if index == 0 { HeroCard(event: event) } else { CompactCard(event: event) }
                        }
                        .buttonStyle(.plain)
                    }
                } else if let failure {
                    EmptyNote(title: "Не получилось загрузить", text: failure)
                    Button("Повторить") { Task { await load() } }
                        .buttonStyle(BigButtonStyle(height: 52))
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .task(id: day + "|" + category) { await load() }
        .refreshable { await load() }
    }

    private var categories: [(String, String)] {
        let order = ["music", "party", "food", "games", "art", "theater", "cinema", "talk", "sport", "walk", "dating"]
        let names = data?.categories ?? [:]
        return order.compactMap { id in names[id].map { (id, $0) } }
    }

    private func load() async {
        failure = nil
        let query = "/events?day=\(day)" + (category.isEmpty ? "" : "&category=\(category)")
        do {
            data = try await API.call("GET", query)
        } catch is CancellationError {
        } catch {
            if data == nil { failure = error.localizedDescription }
        }
    }
}

func lookingText(_ n: Int) -> String { "\(n) " + plural(n, "ищет компанию", "ищут компанию", "ищут компанию") }
func goingText(_ n: Int) -> String { "\(n) " + plural(n, "идёт", "идут", "идут") }

struct HeroCard: View {
    let event: EventCard

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 28) {
                HStack {
                    Badge(text: When.label(event.startsAt))
                    Spacer()
                    Badge(text: event.categoryName, fill: Color.ink.opacity(0.35), ink: .white)
                }
                Text(event.title)
                    .font(.display(26))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(18)
            .frame(minHeight: 196, alignment: .bottom)
            .background(Color.cobalt)

            VStack(alignment: .leading, spacing: 10) {
                Text([event.place, event.price].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.ui(14, .semibold))
                    .foregroundStyle(Color.muted)
                HStack {
                    Text(event.going > 0 ? goingText(event.going) : "Станьте первым гостем")
                        .font(.ui(13, .bold))
                        .foregroundStyle(Color.ink)
                    Spacer()
                    if event.looking > 0 {
                        Text(lookingText(event.looking)).font(.ui(13, .heavy)).foregroundStyle(Color.cobaltInk)
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white)
        }
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
    }
}

struct CompactCard: View {
    let event: EventCard

    var body: some View {
        let colors = Palette.tile(event.id)
        HStack(spacing: 14) {
            Text(event.categoryName)
                .font(.display(12))
                .foregroundStyle(colors.1)
                .multilineTextAlignment(.leading)
                .padding(10)
                .frame(width: 92, height: 92, alignment: .bottomLeading)
                .background(colors.0, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            VStack(alignment: .leading, spacing: 6) {
                Text(When.label(event.startsAt) + (event.price.isEmpty ? "" : " · " + event.price))
                    .font(.ui(12, .heavy))
                    .foregroundStyle(Color.muted)
                    .lineLimit(1)
                Text(event.title)
                    .font(.ui(17, .heavy))
                    .foregroundStyle(Color.ink)
                    .multilineTextAlignment(.leading)
                    .lineLimit(3)
                if event.looking > 0 {
                    Text(lookingText(event.looking)).font(.ui(13, .heavy)).foregroundStyle(Color.cobaltInk)
                } else {
                    Text(event.place).font(.ui(13, .semibold)).foregroundStyle(Color.muted).lineLimit(1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
    }
}
