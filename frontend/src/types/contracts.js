/** @typedef {{id:number,code:string,station:string,planned_at:string,actual_at:string|null,note:string}} Arrival */
/** @typedef {{id:number,name:string,station:string,daily_at:string,recipient:string,enabled:boolean,next_run_at:string}} Subscription */
/** @typedef {{id:number,subscription_id:number,report_day:string,state:string,payload:object,review_note:string}} Receipt */
/** @typedef {{id:number,report_day:string,station:string,stations:string[],state:'pending'|'published'|'rejected',requested_by:string,request_note:string,decision_note:string,basis:object|null,disclosure_id:number|null,disclosure:object|null}} DisclosureApplication */
/** @typedef {{id:number,report_day:string,stations:string[],arrivals:number,delayed:number,delay_minutes:number,published_at:string,version:string,checksum:string,rule:string}} PublicDisclosure */
