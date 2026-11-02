---
name: Project Pi Android UI
description: Existing Flutter Material 3 monitoring interface, documented after the scoped C158 refinement.
colors:
  primary-seed: "#00A884"
  scaffold-dark: "#0B121A"
  surface-dark: "#141D27"
  surface-container-dark: "#18232E"
  surface-container-high-dark: "#1D2935"
  surface-container-highest-dark: "#26333F"
  on-surface-dark: "#E4EBF3"
  on-surface-variant-dark: "#ADBCCB"
  outline-variant-dark: "#304052"
  direction-panel: "#111821"
  direction-line: "#263441"
  direction-text: "#A5ADB9"
  direction-arrow: "#FF3042"
  thermal-notice: "#FFD180"
typography:
  app-bar:
    fontFamily: Roboto
    fontSize: "20px"
    fontWeight: 700
  page-heading:
    fontFamily: Roboto
    fontWeight: 700
  section-heading:
    fontFamily: Roboto
    fontWeight: 700
    letterSpacing: "0.8px"
  direction-label:
    fontFamily: Roboto
    fontSize: "13px"
    fontWeight: 700
    letterSpacing: "0px"
rounded:
  meter: "4px"
  field-image-indicator: "8px"
  palette-option: "12px"
  card: "20px"
spacing:
  compact: "4px"
  inline: "8px"
  group: "12px"
  card-gap: "16px"
  page-inline: "18px"
  panel: "20px"
  page-bottom: "28px"
components:
  monitor-panel:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-surface-dark}"
    rounded: "{rounded.card}"
    padding: "{spacing.panel}"
  thermal-placeholder:
    backgroundColor: "{colors.surface-container-highest-dark}"
    textColor: "{colors.on-surface-dark}"
    rounded: "{rounded.field-image-indicator}"
  palette-option:
    rounded: "{rounded.palette-option}"
    width: "48px"
    height: "48px"
  bottom-navigation:
    backgroundColor: "{colors.surface-dark}"
    height: "72px"
---

# Design System: Project Pi Android UI

## Overview

This documents the incumbent Flutter Material 3 interface after the scoped C158 refinement. The dark interface uses blue-black surfaces, restrained green-derived Material accents, clear headings, and readable sensor states. It is an operating interface for the existing thermal and acoustic monitor; this document introduces no new brand identity or product claims.

The main destinations are Monitor, History, and Controls. Settings remains an app-bar action. Monitoring information, device controls, and the existing emergency presentation retain distinct purposes. Visual changes must preserve delivery, acknowledgement, siren, history, replay, and Android identity/signing behavior.

**Key Characteristics:**

- Dark tonal surfaces with fine borders and no resting card shadow.
- Native Material typography, buttons, inputs, chips, and navigation.
- Explicit waiting, unavailable, disconnected, and last-frame descriptions.
- Flexible wrapping and scrolling instead of compressed content.

This is a source-derived record, not physical-device validation. Reference PNGs for C158 are synthetic Flutter widget renders. The source of truth is `lib/main.dart`, `lib/screens/app_shell.dart`, the three main screens, and their widgets. Values written as `px` in the portable token layer represent Flutter logical pixels; typography is also subject to the platform text scaler.

## Colors

The dark palette combines blue-black neutrals with a Material scheme derived from the existing green seed.

### Primary

- **Primary seed:** input to `ColorScheme.fromSeed`; it is not the resolved primary button or navigation color. Use `Theme.of(context).colorScheme` for generated primary, secondary, error, contrast, and interaction colors rather than treating the seed as the rendered primary.
- **Direction arrow:** a fixed red directional cue when direction is known. It does not itself indicate an emergency.

### Neutral

- **Scaffold dark:** the page and app-bar background.
- **Surface dark:** base dark surface and low container; used by native navigation and flat cards.
- **Surface container dark / high dark / highest dark:** progressively lighter container roles; the highest role provides the empty thermal image background.
- **On surface dark:** main text. **On surface variant dark:** supporting descriptions and unavailable-state labels.
- **Outline variant dark:** dividers and card outlines; both use half opacity in the global theme.
- **Direction panel / line / text:** the fixed dark circular compass, outline, and muted label/unknown arrow.

The warm thermal notice is informational. Connection status uses existing Material amber, green accent, and red accent with text labels. Keyword notices use amber text. Error messages use `colorScheme.error`. Thermal image colors come from the selected thermal color map and its displayed temperature range; they are data encodings, not UI branding.

**The Separate States Rule.** Pi status connectivity, individual stream availability, keyword notice, thermal presence, and emergency state must remain distinguishable. Color accompanies state text or icons.

The light theme remains supported through `ColorScheme.fromSeed` and native defaults. The fixed compass colors remain dark in both themes; this document does not invent a replacement light palette.

## Typography

Roboto is the explicit theme family. No custom font asset is declared in `pubspec.yaml`; retain Flutter/platform font resolution and native text scaling.

- **Page headings:** Material `headlineMedium`, with weight overridden to 700 on Monitor, History, and Controls.
- **App-bar title:** the explicit app-bar token above.
- **Section headings:** Material `titleSmall`, weight 700, with the section-heading tracking token. Uppercase is used for compact Monitor section labels.
- **Card titles and readings:** Material `titleLarge` or `titleMedium`, depending on the component. Reusable status values use `titleMedium` at weight 700.
- **Descriptions and labels:** the existing Material body and label roles. Supporting text uses the variant foreground color.
- **Direction label:** the explicit direction-label token above.

Unspecified sizes, line heights, and Material label styles remain framework-derived. Do not introduce a parallel type scale or force fixed-height text containers.

## Layout

`AppPage` is a vertically scrolling, top-centered column. It has 18 logical pixels of horizontal padding, 20 above, 28 below, and a maximum content width of 1000. Card theme margins provide a 16-pixel bottom gap. Monitor panels use 20-pixel internal padding; other retained cards use 14 or 16 as implemented.

Monitor switches at **720 usable content pixels**, measured after page padding and any rail allocation. Below that width it stacks Direction, Thermal, then Microphones. At or above it, Thermal occupies the left side and Direction/Microphones the right side in a 6:5 flex split with a 16-pixel gutter. This is a content breakpoint, not the app window width.

The shell switches from the 72-pixel bottom navigation bar to a labeled navigation rail at **840 overall layout pixels**. Both expose Monitor, History, and Controls. Settings remains available in the app bar. The alert-link banner sits above destination content, while the emergency overlay sits above the entire shell.

Within the direction panel, the compass is 148 pixels below 400 usable panel pixels and 200 otherwise. The panel stacks its description and compass below 290 usable pixels or above a 1.3 text-scale factor. Light patterns switch from a segmented control to a dropdown below 440 usable pixels or above a 1.3 text-scale factor. Palette options, status chips, history header actions, and power actions wrap.

## Elevation & Depth

Main cards are flat (`elevation: 0`). Tonal layers, the half-opacity outline, spacing, and rounded boundaries establish grouping. The app bar explicitly removes its surface tint. Buttons, input focus states, menus, dialogs, and other native Material elements retain their framework behavior; this is not a custom shadow system.

## Shapes

Cards use the shared 20-pixel corner radius. Thermal images, input theme borders, navigation indicators, and the three selected-indicator swatches use the smaller 8-pixel radius. Palette options use 12-pixel corners. The thermal scale and microphone bars use 4-pixel corners. The direction compass and connection dots remain circular.

Use the theme for recurring card geometry. Some retained Settings fields explicitly supply `OutlineInputBorder` and therefore retain their own Material defaults; do not assume every field resolves to the global input radius.

## Components

### Buttons and fields

Filled and outlined buttons have a theme minimum size of 48 by 48 logical pixels; retain native interaction, focus, and disabled styling. Settings uses filled connection and outlined disconnection actions, labeled host/port/token fields, and existing error text. Destructive device power actions remain separated and confirmed. Shutdown uses the scheme error role. History clearing remains a tonal action with an explicit confirmation dialog and connection gating.

### Cards and sensor states

Monitor panels group connection, direction, thermal, and microphone information. Thermal content uses a 4:3 image, color scale with endpoint labels, and compact coverage/boost readings. The obsolete PART/None reading is absent from the Monitor card; no detection policy is inferred from its removal.

A live thermal frame requires a frame, no thermal error, and a connected thermal socket. Errors show **Sensor unavailable**. Disconnection shows **No live stream**. Retained imagery is explicitly labeled as the last received frame. Coverage and boost show an em dash when not live; a retained pixel reading says **LAST SELECTED PIXEL**. With no frame, the image says **Waiting for thermal stream**.

Microphone levels require a frame, no frame error, and a connected audio socket. Waiting, connecting, and unavailable states have explicit text. Unavailable numeric levels show an em dash and expose an unavailable semantics label. A zero-filled bar in that state must not be described as measured silence. An audio error removes stale direction unless an existing keyword notice supplies the direction context.

### Direction and notices

The circular direction widget contains a single rotating arrow and a label. Unknown direction uses the muted arrow and **NO DIRECTION**. Its rotation uses the existing 240-millisecond ease-out cubic transition. Listening/waiting, keyword spotting, and thermal presence notices remain text-and-icon indicators within the monitoring view.

### Controls and palette

Three indicator selectors and swatches identify the selected indicator. Selected swatches have a 3-pixel primary outline; other swatches use a 1-pixel divider outline. Palette options are 48-pixel square tap targets, arranged with 8-pixel wrapping gaps. Each has a color-name tooltip and selected/button semantics; selection adds a contrasting check icon. Preserve those non-color cues. The palette remains the implemented Material red, orange, amber, yellow, lime, green, cyan, light blue, blue, purple, pink, and white choices.

Brightness is a native slider with a percent label. Light patterns use the responsive segmented-control/dropdown treatment described above. The simulation action and Refresh KWS Service action are absent from the main destinations; Training is not a navigation destination.

### History

An empty history has a centered history icon, **No alerts yet**, and an explanatory line. Populated history keeps native list rows, timestamps, displayed confidence, and recorded human status. The main screen presents up to 12 records. These are existing record fields, not evidence of accuracy or physical validation.

### Emergency presentation

The existing full-screen red emergency overlay remains separate from routine direction, keyword, and thermal notices. It retains white emergency typography, the warning icon, event detail, available thermal capture, its existing pulse animation, and the explicit dismiss action. The alert-link failure banner remains a distinct error surface above content. Visual documentation does not redefine the conditions for either presentation or change acknowledgement, siren, recovery, or replay behavior.

## Do's and Don'ts

### Do:

- **Do** reuse the Flutter theme and the implemented Material components.
- **Do** distinguish the 720-pixel content breakpoint from the 840-pixel shell breakpoint.
- **Do** retain explicit unavailable and last-frame wording alongside sensor data.
- **Do** preserve native text scaling, scrolling, wrapping, labeled selection, and 48-pixel palette targets.
- **Do** keep routine notices visually and behaviorally separate from the existing emergency overlay.

### Don't:

- **Don't** treat the primary seed as a hard-coded replacement for generated Material colors.
- **Don't** label stale or unavailable sensor values as live readings.
- **Don't** restore PART/None, simulation, Training navigation, or Refresh KWS Service to the scoped main interface.
- **Don't** infer new recognition thresholds, alarm policy, accuracy claims, or hardware validation from this visual refinement.
- **Don't** change delivery, acknowledgement, siren, history, replay, or Android identity/signing behavior as part of applying these visual rules.
