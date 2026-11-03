# Vercel

Non-interactive flags: `--non-interactive` is global, and the CLI turns it on automatically when it detects an agent. Commands that otherwise ask for confirmation take `--yes`.

## Auth check
```bash
vercel whoami
vercel project ls; vercel ls          # linked project and recent deployments
```

## Deploy
```bash
vercel                                # preview (same as `vercel deploy`)
vercel build && vercel deploy --prebuilt
vercel inspect <id|url> --wait --timeout 5m   # exits 124 if the wait times out
vercel --prod                         # production, only on explicit intent
vercel promote <id|url>               # make an existing preview the production deployment
```
The **first** deploy of a new project goes to production even without `--prod`. Warn the user before running it.

## Env vars
```bash
vercel env ls [production|preview|development]
vercel env add NAME production < value.txt        # reads the value from stdin, keeping it out of argv
vercel env rm NAME production --yes
vercel env pull .env.local --yes                  # never commit the result
```
A changed env var only takes effect after the next deploy.

## Health check
Vercel has no health-probe setting. Run `curl -fsS -o /dev/null -w '%{http_code}' https://<url>/api/health` after `inspect --wait`.

## Logs
Since CLI v64, logs are a time-window query: `--follow` is deprecated and a positional deployment argument no longer works.
```bash
vercel logs --deployment <id|url> --since 1h
vercel logs --environment production --query 'level:error' --since 30m --json
```

## Rollback
```bash
vercel rollback [<id|url>]            # production goes back to a previous deployment, without a rebuild
vercel rollback status
vercel promote <id|url>               # undoes a rollback
vercel redeploy <id|url>              # rebuilds the same source; this is not a rollback
```
On the Hobby plan you can only roll back to the deployment immediately before the current one.
