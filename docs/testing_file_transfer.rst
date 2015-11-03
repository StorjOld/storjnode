If you want to try out file transfer the commands and explanation are as follows:


1. Host a file on Alice.
> python2.7 storjnode --passive_port 50501 --storage_path /home/laurence/Storj/Alice host_file /home/laurence/Firefox_wallpaper.png

This instructs Storjnode to copy Firefox wallpaper to the folder designated by storage_path. Files "hosted" in this way will be able to be downloaded by other nodes.

Sample output: {'data_id': 'ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab', 'file_size': 2631451}

2. Tell Alice to accept file transfers.
> python2.7 storjnode --passive_port 50501 --storage_path /home/laurence/Storj/Alice run

Alice's server is now running and will be able to process data requests. 

Sample output : UNL = ...

3. Tell Bob to download Alice's file.
> python2.7 storjnode --passive_port 50502 --storage_path /home/laurence/Storj/Bob download data_id_from_step_1 file_size_from_step_1 unl_value_from_step_2



