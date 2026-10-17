# Everything the voice loop transcribed, commands and other speech alike.

# stamp: when the person started speaking (receipt time for text input).
std_msgs/Header header

string text
float32 asr_ms             # speech recognition time; 0 for text input

bool has_direction
float32 direction          # radians, REP-103: 0 ahead, positive to the left
string direction_label     # for people, for example "front-right (45 deg)"
