// OpenCC 简繁转换数据的消费端入口:librime 运行时从 Rime 数据目录下的
// `opencc/` 子目录读取这些文件——`simplifier` 过滤器把 schema 里的
// `opencc_config`(如 `t2s.json`)相对 `<shared_data_dir>/opencc/` 与
// `<user_data_dir>/opencc/` 解析,librime-lua 的 `Opencc` 类用同样的两级顺序,
// 找不到时简繁转换静默失效,只在日志里留一条 "opencc config not found"。
// 本 target 让消费者经由 SwiftPM 拿到这份数据,而不是自己拼装。

import Foundation

public enum RimeOpenCCData {
    /// 携带 `opencc/` 目录的资源包。`.copy` 规则保持目录原样,数据就在
    /// bundle 根下。
    public static var bundle: Bundle { .module }

    /// 把 `opencc/` 数据部署到 `directory` 下,先删除旧拷贝再整目录复制,
    /// 结果落在 librime 查找的唯一位置:`<directory>/opencc/`。返回目标目录。
    ///
    /// `directory` 本身必须是部署时可写的位置;部署之后的 `opencc/` 子树则是
    /// 只读数据——librime 只从 shared 侧读取,写入全部发生在 user 侧与
    /// staging,所以放在此后不再变动的位置也安全。返回目标目录。
    @discardableResult
    public static func deploy(to directory: URL) throws -> URL {
        let source = try dataDirectory()
        let destination = directory.appendingPathComponent("opencc", isDirectory: true)
        let fileManager = FileManager.default
        if fileManager.fileExists(atPath: destination.path) {
            try fileManager.removeItem(at: destination)
        }
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        try fileManager.copyItem(at: source, to: destination)
        return destination
    }

    /// 布局不是预期样子时必须失败,而不是部署出一个空目录让简繁在运行时
    /// 静默失效。
    private static func dataDirectory() throws -> URL {
        if let url = bundle.url(forResource: "opencc", withExtension: nil), isDirectory(url) {
            return url
        }
        if let root = bundle.resourceURL {
            let url = root.appendingPathComponent("opencc", isDirectory: true)
            if isDirectory(url) {
                return url
            }
        }
        throw DeployError.dataNotFound
    }

    private static func isDirectory(_ url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
        return exists && isDirectory.boolValue
    }
}

extension RimeOpenCCData {
    public enum DeployError: LocalizedError {
        case dataNotFound

        public var errorDescription: String? {
            switch self {
            case .dataNotFound:
                return "RimeOpenCCData: opencc directory not found in the resource bundle"
            }
        }
    }
}
