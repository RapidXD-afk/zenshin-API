# Zenshin Supabase API

This is a small, read-only API for the Zenshin mapping database you restored to Supabase. It returns the stored mapping JSON through the compatible endpoints below:

```text
GET /mappings?mal_id=57181
GET /mappings?anilist_id=170942
GET /mappings?thetvdb_id=429934
GET /mappings?anidb_id=18278
```

Successful lookups are cached for six hours, which keeps Supabase egress low for a small MPV user group.

## Render deployment

1. Copy the contents of this folder (`app.py`, `requirements.txt`, and `render.yaml`) into the root of your `RapidXD-afk/zenshin-API` fork, then push them to GitHub. Render's Blueprint flow discovers `render.yaml` at the repository root.
2. In Render, select **New → Blueprint**, then select that repository. Render will use `render.yaml`.
3. Set these Render environment variables:
   - `SUPABASE_URL`: `https://oixyrqkragkqlyhhnlbh.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY`: Supabase Dashboard → Project Settings → API → `service_role` key.
4. After deployment, open `https://<your-service>.onrender.com/health`. It must return `{"status":"ok"}`.
5. Test `https://<your-service>.onrender.com/mappings?mal_id=57779`.
6. Put the service root URL in `nande-rpc.conf`:

   ```ini
   zenshin_api_url=https://<your-service>.onrender.com
   ```

Never put the `service_role` key in the Lua script, its configuration file, GitHub Actions logs, or any client computer.
