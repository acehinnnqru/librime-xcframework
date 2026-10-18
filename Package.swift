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
            url: "https://github.com/acehinnnqru/librime-xcframework/releases/download/1.17.0-pack.0.0.0/librime-static.xcframework.zip",
            checksum: "41b3ce6690407f72cd04bbcebd55a842295818ce5385845f2ba0071592ab5de9"
        ),
        .binaryTarget(
            name: "RimeDynamic",
            url: "https://github.com/acehinnnqru/librime-xcframework/releases/download/1.17.0-pack.0.0.0/librime-dynamic.xcframework.zip",
            checksum: "338954197df7997a2fa482a010dc7042b08497a733175d7649457e8138890e4a"
        ),
        .systemLibrary(
            name: "RimeSystem",
            path: "Sources/RimeSystem",
            pkgConfig: "rime"
        )
    ]
)
