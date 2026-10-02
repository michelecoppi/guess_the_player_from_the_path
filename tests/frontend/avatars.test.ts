import { test } from "node:test";
import assert from "node:assert/strict";
import { Window } from "happy-dom";
import { AVATAR_PATH, bindAvatarPhotos, renderAvatar } from "../../webapp/src/components/Avatar";
import { renderLeaderboardRow } from "../../webapp/src/features/leaderboard/views";

const SIGNED = `${AVATAR_PATH}42?s=0123456789abcdef0123`;

test("avatar: the Telegram photo lies over the initials, decorative and lazy", () => {
  const html = renderAvatar({ name: "Anna", photoUrl: SIGNED });
  assert.ok(html.includes("<span>A</span>"), "the initials stay underneath");
  assert.ok(html.includes(`<img class="avatar-photo" src="${SIGNED}" alt="" loading="lazy" decoding="async" />`));
});

test("avatar: only our own signed path is used as a photo", () => {
  for (const url of ["https://evil.example/a.jpg", "javascript:alert(1)", "/app/api/me", "//evil.example/app/api/avatar/1"]) {
    const html = renderAvatar({ name: "Anna", photoUrl: url });
    assert.ok(!html.includes("<img"), url);
    assert.ok(html.includes("<span>A</span>"));
  }
  assert.ok(!renderAvatar({ name: "Anna" }).includes("<img"));
});

test("avatar: a photo that fails to load removes itself and leaves the initials", () => {
  const window = new Window();
  const document = window.document;
  document.body.innerHTML = renderAvatar({ name: "Anna", photoUrl: SIGNED });
  bindAvatarPhotos(document as unknown as Document);
  const img = document.querySelector("img.avatar-photo")!;
  img.dispatchEvent(new window.Event("error"));
  assert.equal(document.querySelector("img.avatar-photo"), null);
  assert.equal(document.querySelector(".avatar span")?.textContent, "A");
});

test("leaderboard: each row shows the player's photo inside the worn frame", () => {
  const row = renderLeaderboardRow({
    position: 1, profile_id: 42, name: "Giulia", points: 10, avatar: SIGNED,
    frame: { ring: "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)" },
  });
  assert.ok(row.includes('class="ring"'));
  assert.ok(row.includes(`src="${SIGNED}"`));
  assert.ok(!renderLeaderboardRow({ position: 2, profile_id: 43, name: "Dario", points: 9 }).includes("<img"));
});
