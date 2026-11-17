# phase2_step3_demand_test_plan (demand_test_designer)

## hypothesis

Freelance graphic designers in Egypt and the MENA region will pay USD 100 for a digital template pack that helps them track client projects, invoices sent, and revision rounds.

## metric

waitlist_signups

## target

100

## window_days

14

## traffic_sources

```json
[
  "Landing page with a call-to-action to purchase the template pack"
]
```

## reading_rule

ratio = sign-ups / 100. ratio >= 1.0 go; 0.5 to 1.0 repeat; 0.2 to 0.5 pivot; below 0.2 stop.
