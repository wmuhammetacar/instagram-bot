import random
import time
from pathlib import Path

from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    MediaNotFound,
    PrivateError,
    UserNotFound,
)

from insta_bot.security import CooldownRegistry, DelayEngine, LimitEngine, in_window
from insta_bot.targeting import TargetEngine

RESTRICTION_HINTS = ("restrict", "temporarily blocked", "action blocked", "too many")


class Runner:
    """Aksiyon calistiricilari. client; BotClient veya test fake'i (call() arayuzu) olabilir."""

    def __init__(self, config, repo, logger, dry_run=False):
        self.config = config
        self.repo = repo
        self.logger = logger
        self.dry_run = dry_run

    def _engine(self, account_name):
        cfg = self.config.merged_account(account_name)
        return cfg, DelayEngine(cfg), LimitEngine(cfg, self.repo), CooldownRegistry(self.repo)

    def _blocked(self, account_name, cooldowns, *keys):
        return any(cooldowns.active(account_name, k) for k in keys)

    def engage(self, client, account_name, hashtags=None, competitors=None,
               budget=None, like=True, comment=False, max_follows=None):
        cfg, delays, limits, cooldowns = self._engine(account_name)
        summary = {"follows": 0, "likes": 0, "comments": 0, "errors": 0, "skipped": 0}
        if not in_window(cfg, tz_name=self.config.get("system", {}).get("timezone")):
            self.logger.info(f"[{account_name}] Aktivite penceresi disinda, calisma atlandi")
            return summary
        if self._blocked(account_name, cooldowns, "sentry", "restriction"):
            self.logger.warning(f"[{account_name}] Hesap kisitli (cooldown), calisma atlandi")
            summary["skipped"] = 1
            return summary
        budget = budget if budget is not None else int(cfg.get("targeting", {}).get("default_budget_per_run", 20))
        max_follows = max_follows if max_follows is not None else budget

        engine = TargetEngine(self.config, self.repo, self.logger)
        engine.collect(client, account_name, hashtags=hashtags, competitors=competitors)
        followed_set = self.repo.processed_set(account_name, "follow")

        done = 0
        primary_ok = True
        while done < budget and primary_ok:
            if not in_window(cfg, tz_name=self.config.get("system", {}).get("timezone")):
                self.logger.info(f"[{account_name}] Aktivite penceresi kapandi, duruluyor")
                break
            if self._blocked(account_name, cooldowns, "sentry", "restriction"):
                self.logger.warning(f"[{account_name}] Aksiyon kisiti algilandi, duruluyor")
                break
            like_ok = not like or limits.check(account_name, "likes")
            follow_ok = limits.check(account_name, "follows") and len(followed_set) < max_follows
            if not like_ok and not follow_ok:
                self.logger.info(f"[{account_name}] Gunluk limitler doldu, duruluyor")
                break
            targets = self.repo.pending_targets(account_name, limit=1)
            if not targets:
                self.logger.info(f"[{account_name}] Bekleyen hedef kalmadi")
                break
            target = targets[0]
            pk, username = target["pk"], target.get("username") or target["pk"]
            if pk in followed_set:
                self.repo.set_target_status(account_name, pk, "processed")
                continue

            actions_taken = 0
            comment_ok = comment and limits.check(account_name, "comments")
            # Beğeni ve yorum ayni gonderiyi kullanir; medyayi tek sefer cek.
            media_pk = None
            if (like and like_ok) or comment_ok:
                try:
                    medias = client.call("user_medias", pk, amount=1)
                    if medias:
                        media_pk = medias[0].pk
                    else:
                        self.logger.info(f"[{account_name}] @{username} paylasimi yok, atlaniyor")
                except (UserNotFound, MediaNotFound, PrivateError, ClientError) as exc:
                    self._handle_target_error(account_name, pk, exc, summary, cooldowns)

            if like and like_ok and media_pk is not None:
                if not self.repo.is_processed(account_name, "like", media_pk):
                    if self._perform(client, "media_like", media_pk,
                                    account_name=account_name, limit_key="likes", action_key="like",
                                    target_pk=pk, delays=delays, limits=limits, actions_done=done,
                                    cooldowns=cooldowns):
                        summary["likes"] += 1
                        actions_taken += 1
                        done += 1
                        if done >= budget:
                            break

            if follow_ok and pk not in followed_set:
                if self._perform(client, "user_follow", pk,
                                 account_name=account_name, limit_key="follows", action_key="follow",
                                 target_pk=pk, delays=delays, limits=limits, actions_done=done,
                                 cooldowns=cooldowns):
                    summary["follows"] += 1
                    followed_set.add(pk)
                    actions_taken += 1
                    done += 1
                    if done >= budget:
                        break
                else:
                    summary["errors"] += 1

            if comment_ok and media_pk is not None:
                if not self.repo.is_processed(account_name, "comment", media_pk):
                    text = self._render(
                        random.choice(cfg.get("comments", {}).get("rotation", ["Iceriginiz cok guzel!"])),
                        username)
                    if self._perform(client, "media_comment", media_pk, text,
                                    account_name=account_name, limit_key="comments", action_key="comment",
                                    target_pk=pk, delays=delays, limits=limits, actions_done=done,
                                    cooldowns=cooldowns):
                        summary["comments"] += 1
                        actions_taken += 1
                        done += 1
                        if done >= budget:
                            break
                    else:
                        summary["errors"] += 1

            self.repo.set_target_status(account_name, pk, "processed")
            if actions_taken == 0:
                self.repo.mark_processed(account_name, "follow", pk)
        self.logger.info(f"[{account_name}] Engajman bitti: {summary}")
        return summary

    def _perform(self, client, fn, *args, account_name, limit_key, action_key, target_pk,
                 delays, limits, actions_done=0, cooldowns=None):
        if self.dry_run:
            self.logger.info(f"[KURU CALISMA] [{account_name}] {action_key} -> {args[0]}")
            return True
        try:
            client.call(fn, *args)
        except ChallengeRequired:
            raise
        except (UserNotFound, MediaNotFound, PrivateError) as exc:
            self.repo.record_action(account_name, action_key, target_pk, "fail", str(exc))
            return False
        except ClientError as exc:
            msg = str(exc).lower()
            if any(h in msg for h in RESTRICTION_HINTS):
                if cooldowns is not None:
                    cooldowns.set(account_name, "restriction", 6 * 3600, f"{fn}: {exc}")
                self.logger.warning(f"[{account_name}] Kisit algilandi, 6 saatlik bekleme basladi: {exc}")
            self.repo.record_action(account_name, action_key, target_pk, "fail", str(exc))
            return False
        self.repo.record_action(account_name, action_key, target_pk, "ok")
        self.repo.mark_processed(account_name, action_key, target_pk)
        limits.consume(account_name, limit_key)
        delays.pause(action_key, actions_done, logger=self.logger)
        return True

    def _handle_target_error(self, account_name, pk, exc, summary, cooldowns):
        if isinstance(exc, ChallengeRequired):
            raise
        msg = str(exc).lower()
        if any(h in msg for h in RESTRICTION_HINTS):
            cooldowns.set(account_name, "restriction", 6 * 3600, f"target-error: {exc}")
        self.logger.warning(f"[{account_name}] Hedef @{pk} hatasi: {exc}")
        self.repo.set_target_status(account_name, pk, "skipped")
        summary["errors"] += 1

    def dm(self, client, account_name, usernames=None, list_file=None, budget=None):
        cfg, delays, limits, cooldowns = self._engine(account_name)
        summary = {"dms": 0, "errors": 0}
        if self._blocked(account_name, cooldowns, "sentry", "restriction", "dm_restrict"):
            self.logger.warning(f"[{account_name}] DM kisitli, atlaniyor")
            return summary
        rotation = cfg.get("dm", {}).get("rotation", [])
        if not rotation:
            raise ValueError("dm.rotation bos (config.yaml)")
        names = list(usernames or [])
        if list_file:
            for line in Path(list_file).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    names.append(line)
        budget = budget if budget is not None else int(cfg.get("limits", {}).get("dms", 20))
        done = 0
        for name in names:
            name = name.lstrip("@")
            if not name:
                continue
            if done >= budget or not limits.check(account_name, "dms"):
                self.logger.info(f"[{account_name}] DM limiti doldu")
                break
            try:
                uid = client.call("user_id_from_username", name)
            except (UserNotFound, ClientError) as exc:
                self.logger.warning(f"[{account_name}] @{name} bulunamadi: {exc}")
                summary["errors"] += 1
                continue
            if self.repo.is_processed(account_name, "dm", uid):
                self.logger.info(f"[{account_name}] @{name} daha once mesajlanmis, atlandi")
                continue
            text = self._render(random.choice(rotation), name)
            if self._perform(client, "direct_send", text, [uid],
                             account_name=account_name, limit_key="dms", action_key="dm",
                             target_pk=uid, delays=delays, limits=limits,
                             actions_done=done, cooldowns=cooldowns):
                summary["dms"] += 1
                done += 1
        self.logger.info(f"[{account_name}] DM isi bitti: {summary}")
        return summary

    def unfollow(self, client, account_name, budget=None, grace_days=None, keep_followers=None):
        """Gecmiste takip edilip belirli sureden sonra geri takip etmeyenleri birak.

        keep_followers=True ise bizi geri takip edenler korunur (ekstra API cagrisi).
        """
        cfg, delays, limits, cooldowns = self._engine(account_name)
        summary = {"unfollows": 0, "kept": 0, "errors": 0, "skipped": 0}
        if not in_window(cfg, tz_name=self.config.get("system", {}).get("timezone")):
            self.logger.info(f"[{account_name}] Aktivite penceresi disinda, unfollow atlandi")
            return summary
        if self._blocked(account_name, cooldowns, "sentry", "restriction"):
            self.logger.warning(f"[{account_name}] Hesap kisitli (cooldown), unfollow atlandi")
            summary["skipped"] = 1
            return summary

        ucfg = cfg.get("unfollow", {}) or {}
        grace_days = grace_days if grace_days is not None else int(ucfg.get("grace_days", 3))
        keep_followers = keep_followers if keep_followers is not None else bool(ucfg.get("keep_followers", True))
        budget = budget if budget is not None else int(ucfg.get("budget", cfg.get("limits", {}).get("follows", 40)))

        cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - grace_days * 86400))
        candidates = self.repo.unfollow_candidates(account_name, cutoff, limit=max(budget * 3, 50))
        if not candidates:
            self.logger.info(f"[{account_name}] Unfollow icin uygun aday yok (bekleme: {grace_days} gun)")
            return summary

        done = 0
        for pk in candidates:
            if done >= budget or not limits.check(account_name, "unfollows"):
                self.logger.info(f"[{account_name}] Unfollow butcesi/limiti doldu")
                break
            if not in_window(cfg, tz_name=self.config.get("system", {}).get("timezone")):
                self.logger.info(f"[{account_name}] Aktivite penceresi kapandi, unfollow duruluyor")
                break
            if self._blocked(account_name, cooldowns, "sentry", "restriction"):
                self.logger.warning(f"[{account_name}] Aksiyon kisiti algilandi, unfollow duruluyor")
                break

            if keep_followers and not self.dry_run:
                try:
                    friendship = client.call("user_friendship", pk)
                    if getattr(friendship, "followed_by", False):
                        summary["kept"] += 1
                        continue
                except (UserNotFound, ClientError) as exc:
                    self.logger.warning(f"[{account_name}] @{pk} iliskisi alinamadi, atlaniyor: {exc}")
                    summary["errors"] += 1
                    continue

            if self._perform(client, "user_unfollow", pk,
                             account_name=account_name, limit_key="unfollows", action_key="unfollow",
                             target_pk=pk, delays=delays, limits=limits, actions_done=done,
                             cooldowns=cooldowns):
                summary["unfollows"] += 1
                done += 1
            else:
                summary["errors"] += 1
        self.logger.info(f"[{account_name}] Unfollow bitti: {summary}")
        return summary

    @staticmethod
    def _render(template, username):
        return template.replace("{username}", username)
