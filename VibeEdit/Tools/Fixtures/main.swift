import VibeEditTestSupport
import Foundation

@main
enum Fixtures {
    static func main() async {
        guard CommandLine.arguments.count == 2 else {
            FileHandle.standardError.write(Data("usage: vibeedit-fixtures <new-output.mp4>\n".utf8))
            exit(1)
        }
        do {
            let destination = URL(fileURLWithPath: CommandLine.arguments[1])
            try await SyntheticMovie.write(to: destination)
            print("Generated \(destination.path)")
        } catch {
            FileHandle.standardError.write(Data("error: \(error)\n".utf8))
            exit(1)
        }
    }
}
