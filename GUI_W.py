import customtkinter as ctk
from tkinter import filedialog, messagebox
from ultralytics import YOLO
import cv2
import cvzone
import threading
import time
from datetime import datetime, timedelta
import csv, os, pandas as pd

# ----------------------- CONFIG -----------------------
MODEL_PATH   = "best.pt"
TRACKER_CFG  = "bytetrack.yaml"
LOG_FILE     = "ppe_log.csv"

# ----------------------- MODEL -----------------------
model = YOLO(MODEL_PATH)

# ----------------------- STATE -----------------------
stop_flag = False
person_states = {}
PPE_ITEMS = ["Hardhat", "Safety Vest", "Gloves", "Mask"]
NO_PPE_MAP = {"NO-Hardhat": "Hardhat", "NO-Safety Vest": "Safety Vest", "NO-Mask": "Mask"}
CLASS_NAMES = [
    'Excavator','Gloves','Hardhat','Ladder','Mask','NO-Hardhat','NO-Mask','NO-Safety Vest',
    'Person','SUV','Safety Cone','Safety Vest','bus','dump truck','fire hydrant','machinery',
    'mini-van','sedan','semi','trailer','truck and trailer','truck','van','vehicle','wheel loader'
]
BOX_COLOR = (0,0,255)

# ----------------------- UTILITIES -----------------------
def reset_state(): person_states.clear()

def box_center(x1,y1,x2,y2): return ((x1+x2)//2, (y1+y2)//2)
def point_in_box(px,py,bx1,by1,bx2,by2): return bx1<=px<=bx2 and by1<=py<=by2

def associate_to_person(ppe_box,people_boxes):
    x1,y1,x2,y2 = ppe_box
    cx,cy = box_center(x1,y1,x2,y2)
    best_tid,best_area=None,None
    for tid,(px1,py1,px2,py2) in people_boxes.items():
        if point_in_box(cx,cy,px1,py1,px2,py2):
            area=(px2-px1)*(py2-py1)
            if best_area is None or area<best_area:
                best_area=area; best_tid=tid
    return best_tid

def compute_unique_counts():
    wearing={k:0 for k in PPE_ITEMS}
    not_wearing={k:0 for k in PPE_ITEMS if k!="Gloves"}
    for st in person_states.values():
        for i in PPE_ITEMS:
            if st["ppe"].get(i,False): wearing[i]+=1
        for i in not_wearing.keys():
            if st["no"].get(i,False): not_wearing[i]+=1
    return wearing,not_wearing

# ----------------------- LOGGING -----------------------
def log_daily_summary(wear,nowear):
    today=datetime.now().strftime("%Y-%m-%d")
    data={"date":today,"hardhat_not":nowear.get("Hardhat",0),
          "vest_not":nowear.get("Safety Vest",0),
          "mask_not":nowear.get("Mask",0),"gloves_not":0}
    file_exists=os.path.isfile(LOG_FILE)
    with open(LOG_FILE,"a",newline="") as f:
        w=csv.DictWriter(f,fieldnames=data.keys())
        if not file_exists: w.writeheader()
        w.writerow(data)
    print(f"Logged PPE summary for {today}")

def get_weekly_summary():
    if not os.path.isfile(LOG_FILE): return "No data logged yet."
    df=pd.read_csv(LOG_FILE); df["date"]=pd.to_datetime(df["date"])
    today=datetime.now(); week_ago=today-timedelta(days=7)
    df_week=df[df["date"]>=week_ago]
    if df_week.empty: return "No records found for this week."
    total_h, total_v, total_m = df_week["hardhat_not"].sum(), df_week["vest_not"].sum(), df_week["mask_not"].sum()
    total_entries=len(df_week)
    summary=(f"📅 *Weekly PPE Non-Compliance Report*\n\n"
             f"🧾 Period: {week_ago.strftime('%Y-%m-%d')} → {today.strftime('%Y-%m-%d')}\n\n"
             f"🚫 Hardhat Violations: {total_h}\n"
             f"🚫 Safety Vest Violations: {total_v}\n"
             f"🚫 Mask Violations: {total_m}\n\n"
             f"📈 Total Days Logged: {total_entries}\n"
             "📡 Generated automatically by YOLOv8 PPE Monitoring System.")
    return summary

# ----------------------- DETECTION -----------------------
def run_tracking(source,ui_labels):
    global stop_flag
    stop_flag=False; reset_state()
    cap=cv2.VideoCapture(source); cap.set(3,1280); cap.set(4,720)
    if not cap.isOpened():
        messagebox.showerror("Error","Could not open video source!"); return

    for result in model.track(source=source,stream=True,persist=True,tracker=TRACKER_CFG,conf=0.25):
        if stop_flag: break
        frame=result.orig_img.copy(); people_boxes={}
        if result.boxes.id is not None:
            for b in result.boxes:
                cls=int(b.cls[0]); label=CLASS_NAMES[cls]
                tid=int(b.id[0]) if b.id is not None else None
                if tid is None: continue
                x1,y1,x2,y2=map(int,b.xyxy[0]); w,h=x2-x1,y2-y1
                conf=float(b.conf[0]) if b.conf is not None else 0.0
                cvzone.cornerRect(frame,(x1,y1,w,h))
                cvzone.putTextRect(frame,f"{label} {conf:.2f} ID:{tid}",(x1,y1-10),
                                   scale=1,thickness=1,colorR=BOX_COLOR)
                if label=="Person":
                    people_boxes[tid]=(x1,y1,x2,y2)
                    if tid not in person_states:
                        person_states[tid]={"ppe":{k:False for k in PPE_ITEMS},
                                            "no":{k:False for k in ["Hardhat","Safety Vest","Mask"]}}

        if result.boxes is not None and hasattr(result.boxes,"id"):
            for b in result.boxes:
                cls=int(b.cls[0]); label=CLASS_NAMES[cls]
                if label not in PPE_ITEMS and label not in NO_PPE_MAP: continue
                x1,y1,x2,y2=map(int,b.xyxy[0])
                tid=associate_to_person((x1,y1,x2,y2),people_boxes)
                if tid is None: continue
                if label in PPE_ITEMS:
                    person_states[tid]["ppe"][label]=True
                elif label in NO_PPE_MAP:
                    base=NO_PPE_MAP[label]
                    person_states[tid]["no"][base]=True
                    person_states[tid]["ppe"][base]=False

        wear,nowear=compute_unique_counts()
        ui_labels["hardhat_w"].configure(text=f"Hardhat ✓ : {wear['Hardhat']}")
        ui_labels["vest_w"].configure(text=f"Safety Vest ✓ : {wear['Safety Vest']}")
        ui_labels["gloves_w"].configure(text=f"Gloves ✓ : {wear['Gloves']}")
        ui_labels["mask_w"].configure(text=f"Mask ✓ : {wear['Mask']}")
        ui_labels["hardhat_n"].configure(text=f"Hardhat ✗ : {nowear.get('Hardhat',0)}")
        ui_labels["vest_n"].configure(text=f"Safety Vest ✗ : {nowear.get('Safety Vest',0)}")
        ui_labels["mask_n"].configure(text=f"Mask ✗ : {nowear.get('Mask',0)}")

        cv2.imshow("YOLOv8 PPE Detection",frame)
        if cv2.waitKey(1)&0xFF==ord('q'): break

    cap.release(); cv2.destroyAllWindows()
    wear,nowear=compute_unique_counts(); log_daily_summary(wear,nowear)

    total_people=max(wear["Hardhat"]+nowear.get("Hardhat",0),1)
    hardhat_c=(wear["Hardhat"]/total_people)*100
    vest_c=(wear["Safety Vest"]/max(wear["Safety Vest"]+nowear.get("Safety Vest",0),1))*100
    mask_c=(wear["Mask"]/max(wear["Mask"]+nowear.get("Mask",0),1))*100

    summary=(f"🦺 *PPE Detection Summary* ({datetime.now():%Y-%m-%d %H:%M:%S})\n\n"
             f"👷 Hardhat: {wear['Hardhat']} / {nowear.get('Hardhat',0)}  →  {hardhat_c:.1f}% compliant\n"
             f"🦺 Safety Vest: {wear['Safety Vest']} / {nowear.get('Safety Vest',0)}  →  {vest_c:.1f}% compliant\n"
             f"🧤 Gloves: {wear['Gloves']} wearing\n"
             f"😷 Mask: {wear['Mask']} / {nowear.get('Mask',0)}  →  {mask_c:.1f}% compliant\n\n"
             "📡 Generated automatically by YOLOv8 PPE Monitoring System.")
    print(summary)

# ----------------------- GUI -----------------------
def choose_video():
    p=filedialog.askopenfilename(title="Select Video",filetypes=[("Video","*.mp4 *.avi *.mov *.mkv")])
    if p: start_thread(p)
def use_webcam(): start_thread(0)
def start_thread(src): threading.Thread(target=run_tracking,args=(src,ui_labels),daemon=True).start()
def stop_detection():
    global stop_flag; stop_flag=True; messagebox.showinfo("Stopped","Detection/Tracking stopped.")
def show_weekly_report():
    messagebox.showinfo("Weekly Summary", get_weekly_summary())

ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("blue")
root=ctk.CTk(); root.title("🦺 YOLOv8 PPE Detection")
try: root.state("zoomed")
except: root.geometry("1024x700")
root.minsize(900,600)

header=ctk.CTkFrame(root,corner_radius=0,fg_color="#0a0a0a"); header.pack(fill="x")
ctk.CTkLabel(header,text="Protecto.AI.",
             font=("Arial Rounded MT Bold",26),text_color="#00bcd4").pack(pady=20)

btn_frame=ctk.CTkFrame(root,corner_radius=10); btn_frame.pack(pady=10)
btn_frame.columnconfigure((0,1,2,3),weight=1,uniform="buttons")
ctk.CTkButton(btn_frame,text="🎥 Run on Video",height=45,font=("Arial",16),command=choose_video)\
    .grid(row=0,column=0,padx=15,pady=10,sticky="ew")
ctk.CTkButton(btn_frame,text="📸 Run on Webcam",height=45,font=("Arial",16),fg_color="#00b894",command=use_webcam)\
    .grid(row=0,column=1,padx=15,pady=10,sticky="ew")
ctk.CTkButton(btn_frame,text="🛑 Stop Detection",height=45,font=("Arial",16),fg_color="#d63031",command=stop_detection)\
    .grid(row=0,column=2,padx=15,pady=10,sticky="ew")
ctk.CTkButton(btn_frame,text="📅 Weekly Report",height=45,font=("Arial",16),fg_color="#0984e3",command=show_weekly_report)\
    .grid(row=0,column=3,padx=15,pady=10,sticky="ew")

dash=ctk.CTkFrame(root,corner_radius=15,fg_color="#1a1a1a"); dash.pack(padx=25,pady=20,fill="both",expand=True)
ctk.CTkLabel(dash,text="📊 PPE Compliance Summary",
             font=("Arial Rounded MT Bold",22),text_color="#03a9f4").pack(pady=20)

row1,row2=ctk.CTkFrame(dash,fg_color="transparent"),ctk.CTkFrame(dash,fg_color="transparent")
row1.pack(pady=10,fill="x"); row2.pack(pady=10,fill="x")

ui_labels={}
ui_labels["hardhat_w"]=ctk.CTkLabel(row1,text="Hardhat ✓ : 0",font=("Arial",18))
ui_labels["vest_w"]=ctk.CTkLabel(row1,text="Safety Vest ✓ : 0",font=("Arial",18))
ui_labels["gloves_w"]=ctk.CTkLabel(row1,text="Gloves ✓ : 0",font=("Arial",18))
ui_labels["mask_w"]=ctk.CTkLabel(row1,text="Mask ✓ : 0",font=("Arial",18))
for i,l in enumerate(["hardhat_w","vest_w","gloves_w","mask_w"]):
    ui_labels[l].grid(row=0,column=i,padx=25,pady=10,sticky="w")

ui_labels["hardhat_n"]=ctk.CTkLabel(row2,text="Hardhat ✗ : 0",font=("Arial",18),text_color="#ff5252")
ui_labels["vest_n"]=ctk.CTkLabel(row2,text="Safety Vest ✗ : 0",font=("Arial",18),text_color="#ff5252")
ui_labels["mask_n"]=ctk.CTkLabel(row2,text="Mask ✗ : 0",font=("Arial",18),text_color="#ff5252")
for i,l in enumerate(["hardhat_n","vest_n","mask_n"]):
    ui_labels[l].grid(row=0,column=i,padx=25,pady=10,sticky="w")

footer=ctk.CTkFrame(root,fg_color="transparent"); footer.pack(pady=15)
ctk.CTkLabel(footer,text="@protecto.ai",
             font=("Arial",13),text_color="gray").pack()

root.mainloop()
