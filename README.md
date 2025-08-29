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
