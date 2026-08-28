# WealthBuilder Founder Operations Runbook

## Certified release boundary

This release is for one founder operating a research and oversight console. The Bridge may read broker account, position, symbol, market, and history data. Live trading, paper trading, autonomous execution, and external-capital operation remain disabled until separately approved and certified.

## Daily startup

1. Open the VaultMarkets MetaTrader 5 terminal and confirm the founder account is signed in.
2. Run `scripts\Start-WealthBuilderBridge.ps1` from PowerShell.
3. Run `scripts\Test-WealthBuilderBridge.ps1` in a second PowerShell window.
4. Start the WealthBuilder console and confirm it reports **Bridge Operational** and **Risk Safeguarded**.

## Safe recovery

If the console reports **Standby**:

1. Keep all execution controls locked.
2. Confirm VaultMarkets MT5 is open and connected.
3. Stop and restart only the Bridge worker.
4. Run the readiness script again.
5. If the Bridge remains disconnected, preserve the logs and do not enable any trading flag.

## Security rules

- Never commit `.env`, broker passwords, bearer tokens, or account credentials.
- Bind the Bridge to `127.0.0.1` for founder workstation use unless a secured private network is deliberately configured.
- Use one strong bearer token shared only by the local Bridge and console service.
- Keep `BROKER_TRADING_ENABLED=false`.
- Treat a failed health check as unavailable data, never as permission to bypass a guardrail.

## Release gate

Before any future paper or live execution capability is introduced, require a separate written approval, execution service implementation, broker sandbox testing, independent risk limits, audit logging, emergency-stop testing, and a new Atlas certification stage.
