# Decisions

## `transactions.instrument_id`: the security an event is about

A transaction can be about a security even when none of its legs hold that security. A dividend is paid in cash, so its income leg has a currency and no instrument (the `transaction_legs` CHECK allows only one of the two). Without somewhere else to record it, there would be no way to know which holding paid the dividend.

`transactions.instrument_id` is a nullable column for that security:

- **buy** and **dividend** set it.
- **deposit** leaves it `NULL`.

Legs still carry their own `instrument_id` for the shares themselves, which the `holdings` view sums.
