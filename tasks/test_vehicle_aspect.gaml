model TestVehicleAppearance

global {
    geometry shape <- rectangle(240, 240);
    
    init {
        create vehicle number: 1 {
            location <- {100.0, 100.0};
            v_class <- "car";
            heading <- 0.0; // Facing East
            do setup_appearance;
        }
        create vehicle number: 1 {
            location <- {100.0, 120.0};
            v_class <- "truck";
            heading <- 90.0; // Facing South
            do setup_appearance;
        }
        create vehicle number: 1 {
            location <- {100.0, 140.0};
            v_class <- "bus";
            heading <- 180.0; // Facing West
            do setup_appearance;
        }
        create vehicle number: 1 {
            location <- {100.0, 160.0};
            v_class <- "motorcycle";
            heading <- 270.0; // Facing North
            do setup_appearance;
        }
    }
}

species vehicle {
    string v_class <- "car";
    float heading <- 0.0;
    rgb agent_color <- rgb(2, 132, 199);
    float box_w <- 4.6;
    float box_h <- 2.3;
    
    action setup_appearance {
        if (v_class = "car") {
            agent_color <- rgb(2, 132, 199);
            box_w <- 4.6; box_h <- 2.2;
        } else if (v_class = "truck") {
            agent_color <- rgb(239, 68, 68);
            box_w <- 8.0; box_h <- 2.6;
        } else if (v_class = "bus") {
            agent_color <- rgb(245, 158, 11);
            box_w <- 10.0; box_h <- 2.8;
        } else if (v_class = "motorcycle") {
            agent_color <- rgb(16, 185, 129);
            box_w <- 2.2; box_h <- 1.0;
        }
    }
    
    aspect default {
        // Thân xe mô phỏng thực tế (Chassis)
        draw (rectangle(box_h, box_w) rotated_by heading) color: agent_color border: rgb(51, 65, 85) width: 1.0;
        
        // Kính chắn gió / Cabin xe (Cabin & Windshield glass)
        if (v_class = "car") {
            draw (rectangle(box_h * 0.85, box_w * 0.5) rotated_by heading) color: rgb(30, 41, 59, 200);
        } else if (v_class = "bus") {
            draw (rectangle(box_h * 0.85, box_w * 0.75) rotated_by heading) color: rgb(30, 41, 59, 180);
        } else if (v_class = "truck") {
            // Cabin trước
            draw (rectangle(box_h * 0.9, box_w * 0.3) rotated_by heading) color: rgb(30, 41, 59, 220);
        } else if (v_class = "motorcycle") {
            draw (circle(0.45) at: location) color: rgb(15, 23, 42);
        }
        
        // Đèn pha trước (Headlights)
        point front_pt <- location + {cos(heading - 90) * (box_w / 2.2), sin(heading - 90) * (box_w / 2.2)};
        draw circle(0.35) at: front_pt color: rgb(254, 240, 138);
    }
}

experiment TestExp type: gui {
    output {
        display "Test" type: 2d {
            species vehicle aspect: default;
        }
    }
}
