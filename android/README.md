# TuneLift Android (v1 WebView)

This is the **version 1** Android app for TuneLift. It’s a simple, professional **WebView wrapper** around your hosted TuneLift website.

## What you get

- Modern splash screen (Android 12+ SplashScreen API)
- Dark premium UI feel (Material 3 dark theme)
- Adaptive launcher icon
- Loading indicator + pull-to-refresh
- Offline / connection error handling with Retry
- Back button support (web history)
- File downloads handled via Android DownloadManager

## Set your hosted URL

Edit:

- `app/src/main/res/values/strings.xml` → `tune_lift_url`

## Open & build

1. Open the `android/` folder in **Android Studio**.
2. Let Android Studio sync Gradle dependencies.
3. Run on a device/emulator.

## Notes

- This app is intended as a wrapper for your hosted site (v1).
- Later you can replace this with a full native Flutter app.
- Current `minSdk` is **26** to keep the project fully text-based (no legacy PNG launcher icons committed).

