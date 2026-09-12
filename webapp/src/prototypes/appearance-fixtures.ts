/** Snapshots from services/shop.py::appearance (it), checked by test_appearance_contract.py. */
import type { ResolvedAppearance } from "@/appearance";
import snapshots from "./appearance-fixtures.json";
export const appearanceFixtures = snapshots satisfies Record<string, ResolvedAppearance>;
export type AppearanceFixtureName = keyof typeof appearanceFixtures;
