// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Librime",
    platforms: [
        .macOS(.v11),
        .iOS(.v15)
    ],
    products: [
        .library(name: "Rime", targets: ["RimeHeaders"]),
        .library(name: "RimeStatic", targets: ["RimeStatic"]),
        .library(name: "RimeDynamic", targets: ["RimeDynamic"]),
        .library(name: "RimeDynamicStub", targets: ["RimeDynamicStub"]),
        .library(name: "RimeSystem", targets: ["RimeSystem"]),
        .library(name: "RimeOpenCCData", targets: ["RimeOpenCCData"])
    ],
    targets: [
        .systemLibrary(
            name: "RimeHeaders",
            path: "Sources/RimeHeaders/include"
        ),
        .target(
            name: "RimeDynamicStub",
            path: "Sources/RimeDynamicStub",
            linkerSettings: [
                .linkedFramework("RimeDynamic")
            ]
        ),
        .target(
            name: "RimeOpenCCData",
            path: "Sources/RimeOpenCCData",
            resources: [
                .copy("opencc")
            ]
        ),
        .binaryTarget(
            name: "RimeStatic",
            url: "https://github.com/ghostflyby/librime-xcframework/releases/download/1.17.0-pack.10.0.0/librime-static.xcframework.zip",
            checksum: "9e9923112ee9cee9bb53c25b41e51a2d7ea2ab3d91f34c7c99682224a23718ac"
        ),
        .binaryTarget(
            name: "RimeDynamic",
            url: "https://github.com/ghostflyby/librime-xcframework/releases/download/1.17.0-pack.10.0.0/librime-dynamic.xcframework.zip",
            checksum: "5beaca3b6263e8ddc4a053eaebe4a0de2e33c2fc36056dd7fa0a8b87edb88533"
        ),
        .systemLibrary(
            name: "RimeSystem",
            path: "Sources/RimeSystem",
            pkgConfig: "rime"
        )
    ]
)
