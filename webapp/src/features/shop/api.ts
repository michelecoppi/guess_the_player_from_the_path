import { api, type ApiClient } from "@/api/client";
import type {
  ShopCatalogueResponse,
  EquipResponse,
  BuyResponse,
  LookAction,
  LookResponse,
  ShopPurchaseHistoryResponse,
} from "./types";

/**
 * Fetches the authoritative shop catalogue from POST /app/api/shop.
 */
export async function fetchShopCatalogue(
  client: ApiClient = api,
): Promise<ShopCatalogueResponse> {
  return client.post<ShopCatalogueResponse>("/app/api/shop", {});
}

/**
 * Equips an owned cosmetic or equippable bundle via POST /app/api/shop/equip.
 * Never sends user ID, slot, or raw style — only the catalogue item ID.
 */
export async function equipShopItem(
  itemId: string,
  client: ApiClient = api,
): Promise<EquipResponse> {
  return client.post<EquipResponse>("/app/api/shop/equip", { item: itemId });
}

/**
 * Requests an invoice link for Telegram Stars purchase via POST /app/api/shop/buy.
 * The client sends only the item ID; the backend resolves pricing and grants.
 */
export async function buyShopItem(
  itemId: string,
  client: ApiClient = api,
): Promise<BuyResponse> {
  return client.post<BuyResponse>("/app/api/shop/buy", { item: itemId });
}

/**
 * Performs a saved-look mutation (save, wear, delete) via POST /app/api/shop/look.
 */
export async function mutateShopLook(
  action: LookAction,
  name: string,
  client: ApiClient = api,
): Promise<LookResponse> {
  return client.post<LookResponse>("/app/api/shop/look", { action, name });
}

/**
 * Fetches user purchase history via POST /app/api/shop/history.
 */
export async function fetchShopHistory(
  client: ApiClient = api,
): Promise<ShopPurchaseHistoryResponse> {
  return client.post<ShopPurchaseHistoryResponse>("/app/api/shop/history", {});
}
