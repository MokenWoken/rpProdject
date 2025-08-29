# rpProdject

Okay so what ive learned is that python3 needs to be installed with packages like pygame and it can then run keyboard commands

I have generated a SSH key on the raspberry pi and put that into the GitHub Settings.
then using git clone git@github.com:MokenWoken/rpProdject.git i can clone the project without any weird password requests.
And to finalize setting up the Project i go:
cd rpProdject
git init
git remote add origin git@github.com:USERNAME/repo.git
git pull origin main   # or master, depending on your branch

I can easily SSH into the raspberry from windows powershell by figuring out the Raspberrys IP and then doing "@USERNAME-OF-PI IP-ADRESS"

In JSON, a sequence stage looks like:

"correct": [["1","2","3","4","5"]]


A normal stage can be:

"correct": "a"


or

"correct": ["a"," "]



[
  {
    "id": "stage1",
    "prompt": ["beginning1.wav"],
    "correct": " ",
    "success": ["spacebar_success_goto_W.wav"],
    "fail": {
      "b": ["beep.wav"]
    },
    "fail_default": ["spacebar_fail1.wav", "spacebar_fail2.wav", "spacebar_fail3.wav", "spacebar_fail4.wav", "spacebar_fail5.wav", "spacebar_fail6_s_request.wav", "spacebar_S_fail7_.wav"],
    
    // optional overrides
    "next_on_success": "stage2",
    "next_on_fail": "game_over",

    // special branch after N fails
    "fail_branches": {
      "6": {
        "keys": {
          "s": "secret_stage_x",
          " ": "stage2"
        }
      }
    }
  },
  {
    "id": "stage2",
    "prompt": ["W_start.wav"],
    "correct": "W",
    "success": ["w_success.wav"],
    "fail_default": ["beep.wav"]
  }
]
