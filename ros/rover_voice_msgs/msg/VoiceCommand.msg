# A recognized voice command, published once per command.
# The voice loop only reports it. The rover's controller decides what to do.

string FOLLOW="FOLLOW"
string STAY="STAY"
string FETCH="FETCH"
string COME="COME"
string GIVE="GIVE"

# stamp: when the person started speaking. frame_id: the array's frame.
std_msgs/Header header

string intent              # one of the constants above
float32 confidence         # 0 to 1
bool by_meaning            # matched by meaning, not by a known phrase
string transcript          # what was heard
string[] slot_keys         # extra details, paired with slot_values
string[] slot_values

# Where the speech came from. False with a plain microphone, or before
# the array is calibrated (scripts/run --doa-calibrate).
bool has_direction
float32 direction          # radians, REP-103: 0 ahead, positive to the left
