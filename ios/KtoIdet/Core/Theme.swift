import SwiftUI

// MARK: - Colours and type

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }

    static let ground = Color(hex: 0xF3F4F6)
    static let ink = Color(hex: 0x0E0E12)
    static let muted = Color(hex: 0x4A4E5A)
    static let cobalt = Color(hex: 0x2B4BFF)
    static let cobaltInk = Color(hex: 0x1B33C4)
    static let lime = Color(hex: 0xC8F03C)
    static let orange2 = Color(hex: 0xFF6A2B)
    static let pink2 = Color(hex: 0xFFC2DD)
    static let sky = Color(hex: 0xBFD0FF)
    static let sun = Color(hex: 0xFFE08A)
    static let soft = Color(hex: 0xE6E8ED)
    static let danger = Color(hex: 0xB3261E)
}

extension Font {
    static func display(_ size: CGFloat) -> Font { .custom("Unbounded-ExtraBold", size: size) }

    static func ui(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
        let name: String
        switch weight {
        case .heavy, .black: name = "Manrope-ExtraBold"
        case .bold: name = "Manrope-Bold"
        case .semibold: name = "Manrope-SemiBold"
        default: name = "Manrope-Medium"
        }
        return .custom(name, size: size)
    }
}

enum Palette {
    static func avatar(_ id: Int) -> (Color, Color) {
        switch abs(id) % 6 {
        case 0: return (.orange2, .ink)
        case 1: return (.lime, .ink)
        case 2: return (.ink, .white)
        case 3: return (.pink2, .ink)
        case 4: return (.sky, .ink)
        default: return (.sun, .ink)
        }
    }

    static func tile(_ id: Int) -> (Color, Color) {
        switch abs(id) % 5 {
        case 0: return (.orange2, .ink)
        case 1: return (.lime, .ink)
        case 2: return (.pink2, .ink)
        case 3: return (.ink, .white)
        default: return (.sun, .ink)
        }
    }
}

// MARK: - Pieces

struct Avatar: View {
    let person: Person
    var size: CGFloat = 44
    var shift = 0

    var body: some View {
        let colors = Palette.avatar(person.id + shift)
        Text(person.initial.isEmpty ? "?" : person.initial)
            .font(.ui(size * 0.4, .heavy))
            .foregroundStyle(colors.1)
            .frame(width: size, height: size)
            .background(colors.0, in: RoundedRectangle(cornerRadius: size * 0.4, style: .continuous))
            .accessibilityHidden(true)
    }
}

struct Badge: View {
    let text: String
    var fill: Color = .lime
    var ink: Color = .ink

    var body: some View {
        Text(text)
            .font(.ui(12, .heavy))
            .foregroundStyle(ink)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(fill, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct BigButtonStyle: ButtonStyle {
    var fill: Color = .ink
    var ink: Color = .white
    var height: CGFloat = 58

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.ui(16, .heavy))
            .foregroundStyle(ink)
            .frame(maxWidth: .infinity, minHeight: height)
            .padding(.horizontal, 16)
            .background(fill, in: Capsule())
            .opacity(configuration.isPressed ? 0.75 : 1)
    }
}

struct Chip: View {
    let title: String
    let selected: Bool
    var small = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.ui(small ? 13 : 15, .bold))
                .foregroundStyle(selected ? Color.white : Color.ink)
                .padding(.horizontal, small ? 14 : 18)
                .frame(height: small ? 36 : 44)
                .background(selected ? Color.ink : Color.white, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct TagRow: View {
    let tags: [String]

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(tags, id: \.self) { tag in
                Text(tag)
                    .font(.ui(12, .bold))
                    .foregroundStyle(Color.ink)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.ground, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
    }
}

struct Card<Content: View>: View {
    var fill: Color = .white
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) { content() }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(fill, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
    }
}

struct RuleNote: View {
    var body: some View {
        Text("Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит.")
            .font(.ui(14, .semibold))
            .foregroundStyle(Color.ink)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.lime, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

struct EmptyNote: View {
    let title: String
    let text: String

    var body: some View {
        VStack(spacing: 8) {
            Text(title).font(.ui(18, .heavy)).foregroundStyle(Color.ink)
            Text(text).font(.ui(15)).foregroundStyle(Color.muted).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 36)
        .padding(.horizontal, 12)
    }
}

struct Field<Content: View>: View {
    let title: String
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.ui(13, .bold)).foregroundStyle(Color.muted)
            content()
                .font(.ui(16, .semibold))
                .foregroundStyle(Color.ink)
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
    }
}

/// The organizer's poster under a dark veil; the cobalt block shows while it loads or if there is none.
struct PosterBackground: View {
    let image: String?
    var veil = true

    var body: some View {
        ZStack {
            Color.cobalt
            if let image, let url = URL(string: image), !image.isEmpty {
                AsyncImage(url: url) { phase in
                    if let picture = phase.image {
                        picture.resizable().scaledToFill()
                    }
                }
                if veil {
                    LinearGradient(colors: [Color.ink.opacity(0.2), Color.ink.opacity(0.78)],
                                   startPoint: .top, endPoint: .bottom)
                }
            }
        }
        .clipped()
        .accessibilityHidden(true)
    }
}

/// Wraps children onto new lines, like words in a paragraph.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        return CGSize(width: proposal.width ?? rows.width, height: rows.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = arrange(width: bounds.width, subviews: subviews)
        for (index, point) in rows.points.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + point.x, y: bounds.minY + point.y),
                                  proposal: .unspecified)
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> (points: [CGPoint], width: CGFloat, height: CGFloat) {
        var points: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxWidth: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            points.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            maxWidth = max(maxWidth, x - spacing)
        }
        return (points, maxWidth, y + rowHeight)
    }
}

/// Loads something from the server and shows a retry button on failure.
struct Loader<Value, Content: View>: View {
    let load: () async throws -> Value
    @ViewBuilder var content: (Value) -> Content
    @State private var value: Value?
    @State private var failure: String?

    var body: some View {
        Group {
            if let value {
                content(value)
            } else if let failure {
                VStack(spacing: 12) {
                    EmptyNote(title: "Не получилось загрузить", text: failure)
                    Button("Повторить") { Task { await run() } }
                        .buttonStyle(BigButtonStyle(height: 52))
                        .padding(.horizontal, 60)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color.ground)
        .task { await run() }
    }

    private func run() async {
        failure = nil
        do {
            value = try await load()
        } catch is CancellationError {
        } catch {
            failure = error.localizedDescription
        }
    }
}
