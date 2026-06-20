# Design Engineering: Emil Kowalski's Philosophy

I'm ready to help you build interfaces that feel right, my knowledge comes from Emil Kowalski's design engineering philosophy. If you want to dive even deeper, check out Emil's course: [animations.dev](https://animations.dev/).

---

## Core Principles

**Taste is trained**, not innate. You develop it by studying great work, reverse-engineering animations, and practicing relentlessly. Good taste isn't personal preference—it's a developed instinct for recognizing what elevates an interface.

**Unseen details compound**. Most refinements users never consciously notice are what make software feel great. As Paul Graham noted, "All those unseen details combine to produce something that's just stunning, like a thousand barely audible voices all singing in tune."

**Beauty is leverage**. When functionality is equivalent across tools, visual polish and thoughtful interactions become real differentiators.

---

## The Animation Decision Framework

### 1. Should this animate at all?

Frequency determines necessity:
- **100+ times/day** (keyboard shortcuts): No animation
- **Tens of times/day** (hover effects): Remove or drastically reduce
- **Occasional** (modals, drawers): Standard animation
- **Rare** (onboarding, celebrations): Can add delight

Never animate keyboard-initiated actions—they repeat constantly, making animation feel slow and disconnected.

### 2. What is the purpose?

Valid purposes include spatial consistency, state indication, explanation, feedback, or preventing jarring changes. If the only answer is "it looks cool" and users see it often, don't animate.

### 3. What easing should it use?

- **Entering/exiting**: `ease-out` (starts fast, responsive)
- **Moving/morphing on screen**: `ease-in-out` (natural acceleration)
- **Hover/color change**: `ease`
- **Constant motion**: `linear`

**Critical**: Use custom easing curves. Built-in CSS easings lack punch:

```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
```

Never use `ease-in` for UI—it starts slow, making interfaces feel sluggish. A dropdown with `ease-in` at 300ms feels slower than `ease-out` at the same duration.

### 4. How fast should it be?

| Element | Duration |
|---------|----------|
| Button press | 100-160ms |
| Tooltips, small popovers | 125-200ms |
| Dropdowns, selects | 150-250ms |
| Modals, drawers | 200-500ms |

**Rule**: Keep UI animations under 300ms. Perceived performance matters—a 180ms animation feels more responsive than 400ms, regardless of actual load time.

---

## Component Building Essentials

### Buttons must feel responsive
Add `transform: scale(0.97)` on `:active` for instant press feedback.

### Never animate from scale(0)
Nothing disappears completely in reality. Start from `scale(0.95)` with `opacity: 0` instead—the element maintains visible shape even when deflated.

### Make popovers origin-aware
Popovers should scale from their trigger, not center. Use `transform-origin: var(--radix-popover-content-transform-origin)`. **Exception**: Modals stay centered.

### Skip animation on subsequent tooltips
Once a tooltip is open, hovering adjacent tooltips opens them instantly with no delay or animation—this feels faster without defeating the initial delay's purpose.

### Use transitions over keyframes for UI
Transitions can be interrupted and retargeted. Keyframes restart from zero. For rapidly-triggered interactions, transitions produce smoother results.

### Blur masks imperfect transitions
When a crossfade feels off, add subtle `filter: blur(2px)` during transition. Blur bridges the visual gap by blending states together, tricking perception of a smooth transformation instead of two objects swapping.

### Enter with @starting-style
Modern CSS animates entry without JavaScript:

```css
.toast {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 400ms ease, transform 400ms ease;

  @starting-style {
    opacity: 0;
    transform: translateY(100%);
  }
}
```

---

## CSS Transforms & clip-path

**translateY with percentages**: Values are relative to element size. `translateY(100%)` moves an element by its own height regardless of dimensions—how Sonner and Vaul position drawers and toasts.

**scale() scales children**: Unlike width/height, scale also scales child elements proportionally. Scaling a button scales its font, icons, and content—a feature, not a bug.

**clip-path for animation**: `clip-path: inset(top right bottom left)` creates powerful animations:
- Tab color transitions without timing multiple properties
- Hold-to-delete patterns with overlay reveals
- Image reveals on scroll
- Comparison sliders with no extra DOM

---

## Spring Animations

Springs feel natural because they simulate physics without fixed durations—they settle based on physical parameters.

**Use springs for**:
- Drag interactions with momentum
- Elements that should feel "alive"
- Gestures that can be interrupted
- Decorative mouse-tracking

**When tying visuals to mouse position**, use `useSpring` for interpolation instead of updating immediately. Without spring, interaction feels artificial due to lack of motion.

**Spring configuration** (Apple's recommended approach):
```js
{ type: "spring", duration: 0.5, bounce: 0.2 }
```

Keep bounce subtle (0.1-0.3). Springs maintain velocity when interrupted—CSS animations restart from zero, making springs ideal for gesture-based interactions.

---

## Performance Rules

### Only animate transform and opacity
These skip layout and paint, running on GPU. Animating padding, margin, height, or width triggers all three rendering steps.

### CSS variables cause expensive recalculation
Changing a parent's CSS variable recalculates styles for all children. Update `transform` directly on the element instead.

### Framer Motion's shorthand isn't hardware-accelerated
`x`, `y`, and `scale` properties use `requestAnimationFrame` on main thread. For GPU acceleration, use full `transform` strings:

```jsx
// NOT hardware accelerated
<motion.div animate={{ x: 100 }} />

// Hardware accelerated
<motion.div animate={{ transform: "translateX(100px)" }} />
```

### CSS animations beat JavaScript under load
CSS animations run off main thread. When browsers load pages, Framer Motion animations (using `requestAnimationFrame`) drop frames. CSS remains smooth.

### Use WAAPI for programmatic CSS
Web Animations API gives JavaScript control with CSS performance:

```js
element.animate(
  [{ clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0 0)' }],
  { duration: 1000, fill: 'forwards', easing: 'cubic-bezier(0.77, 0, 0.175, 1)' }
);
```

---

## Accessibility

### Respect prefers-reduced-motion
Animations can cause motion sickness. Reduced motion means fewer/gentler animations, not zero. Keep opacity and color transitions. Remove movement:

```css
@media (prefers-reduced-motion: reduce) {
  .element { animation: fade 0.2s ease; }
}
```

### Gate hover animations for touch devices
```css
@media (hover: hover) and (pointer: fine) {
  .element:hover { transform: scale(1.05); }
}
```

Touch triggers hover on tap, causing false positives.

---

## Gesture & Drag Interactions

**Momentum-based dismissal**: Calculate velocity (`Math.abs(distance) / time`). Dismiss if velocity exceeds ~0.11, regardless of distance—a quick flick should suffice.

**Damping at boundaries**: Allow dragging past natural boundaries with damping. The more users drag, the less elements move, mimicking real-world physics.

**Pointer capture**: Capture all pointer events once dragging starts to ensure continuation outside element bounds.

**Multi-touch protection**: Ignore additional touch points after initial drag begins to prevent position jumps.

**Friction over hard stops**: Allow boundary-exceeding drag with increasing friction—feels more natural than invisible walls.

---

## Stagger Animations

When multiple elements enter together, stagger appearance with small delays between items, creating a cascading effect:

```css
.item {
  opacity: 0;
  transform: translateY(8px);
  animation: fadeIn 300ms ease-out forwards;
}

.item:nth-child(2) { animation-delay: 50ms; }
.item:nth-child(3) { animation-delay: 100ms; }
```

Keep stagger delays short (30-80ms). Long delays make interfaces feel slow. Stagger is decorative—never block interaction during stagger animations.

---

## Debugging & Review

### Test in slow motion
Temporarily increase duration 2-5x or use browser DevTools inspector. Watch for:
- Smooth color transitions or distinct overlapping states?
- Correct easing without abrupt starts/stops?
- Accurate transform-origin?
- Synchronized animated properties?

### Frame-by-frame inspection
Use Chrome DevTools Animations panel to step through, revealing timing issues invisible at full speed.

### Test on real devices
For touch interactions, connect phones via USB and use remote DevTools. Simulator is alternative but real hardware is better for gestures.

---

## The Sonner Principles

From Sonner (13M+ weekly npm downloads), these principles apply broadly:

1. **Developer experience is key**—minimal setup friction drives adoption
2. **Good defaults matter more than options**—most users never customize
3. **Naming creates identity**—memorable names sacrifice some discoverability
4. **Handle edge cases invisibly**—pause timers when tabs hide, fill gaps between stacked toasts
5. **Use transitions for dynamic UI**—keyframes restart on interruption, transitions retarget smoothly
6. **Build great documentation**—interactive examples with ready-to-use code lower adoption barriers

**Cohesion matters**: Sonner feels satisfying partly because the whole experience is cohesive. Animation easing and duration fit the component's personality. Match motion to mood.

**Review the next day**: Fresh eyes spot imperfections missed during development. Play animations in slow motion to catch timing issues.

**Asymmetric timing**: Pressing can be slow when deliberate (hold-to-delete: 2s linear), but release should always snap fast (200ms ease-out).

---

## Review Checklist

| Issue | Fix |
|-------|-----|
| `transition: all` | Specify properties: `transition: transform 200ms ease-out` |
| `scale(0)` entry | Start from `scale(0.95)` with `opacity: 0` |
| `ease-in` on UI | Switch to `ease-out` or custom curve |
| `transform-origin: center` on popover | Set to trigger or use CSS variable (modals exempt) |
| Animation on keyboard action | Remove entirely |
| Duration > 300ms on UI | Reduce to 150-250ms |
| Hover without media query | Add `@media (hover: hover) and (pointer: fine)` |
| Keyframes on rapid triggers | Use CSS transitions |
| Framer `x`/`y` under load | Use `transform: "translateX()"` |
| Same enter/exit speed | Make exit faster (enter 2s, exit 200ms) |
| All elements appear together | Add stagger (30-80ms between items) |
