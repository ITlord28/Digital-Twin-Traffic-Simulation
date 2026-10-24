model TestGotoRun

global {
    geometry shape <- rectangle(240, 240);
    float step <- 0.1 #s;
    
    init {
        create vehicle number: 1 {
            location <- {125.0, 230.0};
            do setup_trajectory;
        }
    }
}

species vehicle skills: [moving] {
    list<point> waypoints <- [];
    point current_target <- nil;
    float speed_val <- 7.0;
    
    action setup_trajectory {
        waypoints <- [{125.0, 120.0}, {125.0, 0.0}];
        current_target <- waypoints[0];
    }
    
    reflex autonomous_drive {
        write "Cycle " + cycle + " location before: " + location + " target: " + current_target;
        do goto target: current_target speed: speed_val * step;
        write "Cycle " + cycle + " location after : " + location;
        if (cycle >= 5) {
            do pause;
        }
    }
}

experiment TestExp type: gui {}
