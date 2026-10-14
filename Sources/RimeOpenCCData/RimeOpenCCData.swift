// OpenCC 简繁转换数据的消费端入口:librime 运行时从 Rime 数据目录下的
// `opencc/` 子目录读取这些文件——`simplifier` 过滤器把 schema 里的
// `opencc_config`(如 `t2s.json`)相对 `<shared_data_dir>/opencc/` 与
// `<user_data_dir>/opencc/` 解析,librime-lua 的 `Opencc` 类用同样的两级顺序,
// 找不到时简繁转换静默失效,只在日志里留一条 "opencc config not found"。
// 本 target 让消费者经由 SwiftPM 拿到这份数据,而不是自己拼装;数据如何
// 进入 Rime 数据目录由消费端决定。

import Foundation

public enum RimeOpenCCData {
    /// `opencc/` 数据目录在资源包内的 URL。`.copy` 把目录原样放在 bundle
    /// 资源根下,位置按构造成立,不存在失败路径。
    public static var url: URL {
        Bundle.module.resourceURL!
            .appendingPathComponent("opencc", isDirectory: true)
    }
}
