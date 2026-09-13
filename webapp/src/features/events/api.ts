import { api, type ApiClient } from "@/api/client";
import type { EventsResponse } from "./types";
export const fetchEvents = (client:ApiClient=api):Promise<EventsResponse> => client.post("/arena", {mode:"events",action:"get"});
export const guessEvent = (code:string,day:string,answer:string,revision:number,client:ApiClient=api):Promise<EventsResponse> => client.post("/arena", {mode:"events",action:"guess",code,day,answer:answer.trim(),revision});
