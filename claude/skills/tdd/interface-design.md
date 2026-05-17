<!--
Vendored from mattpocock/skills @ e74f0061bb67222181640effa98c675bdb2fdaa7
Upstream path: skills/engineering/tdd/interface-design.md
License: MIT — Copyright (c) 2026 Matt Pocock
Source: https://github.com/mattpocock/skills/blob/e74f0061bb67222181640effa98c675bdb2fdaa7/skills/engineering/tdd/interface-design.md
Do not edit in place — re-vendor from upstream and bump the SHA.
-->

# Interface Design for Testability

Good interfaces make testing natural:

1. **Accept dependencies, don't create them**

   ```typescript
   // Testable
   function processOrder(order, paymentGateway) {}

   // Hard to test
   function processOrder(order) {
     const gateway = new StripeGateway();
   }
   ```

2. **Return results, don't produce side effects**

   ```typescript
   // Testable
   function calculateDiscount(cart): Discount {}

   // Hard to test
   function applyDiscount(cart): void {
     cart.total -= discount;
   }
   ```

3. **Small surface area**
   - Fewer methods = fewer tests needed
   - Fewer params = simpler test setup
